"""Deploy the recipe's agent to Amazon Bedrock AgentCore, and remove it again.

    python deploy.py setup               once per AWS account: the shared credential provider
    python deploy.py deploy NAME         one runtime, with its own execution role
    python deploy.py invoke NAME PROMPT  one request to that runtime
    python deploy.py destroy NAME        the runtime and its role
    python deploy.py teardown            the shared credential provider and the code bucket

It reads its settings from .env (see .env.example) and uses your AWS credentials
(AWS_PROFILE, or boto's default chain). It needs no Highflame credential.
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import uuid
import zipfile

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

RECIPE_DIR = pathlib.Path(__file__).resolve().parent
AGENT_DIR = RECIPE_DIR / "agent"
BUILD_DIR = RECIPE_DIR / "build"
load_dotenv(RECIPE_DIR / ".env")

REGION = os.environ.get("AWS_REGION", "us-east-1")
PROVIDER = os.environ.get("HIGHFLAME_PROVIDER", "highflame-agents")
RUNTIME_PYTHON = "3.12"  # AgentCore's PYTHON_3_12 managed runtime, on Linux ARM64

session = boto3.session.Session(profile_name=os.environ.get("AWS_PROFILE") or None, region_name=REGION)
ACCOUNT = session.client("sts").get_caller_identity()["Account"]
iam = session.client("iam")
control = session.client("bedrock-agentcore-control")


def setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Set {name} in .env (see .env.example).")
    return value.rstrip("/")


def code_bucket() -> str:
    return os.environ.get("CODE_BUCKET") or f"highflame-agentcore-code-{ACCOUNT}-{REGION}"


def role_name(name: str) -> str:
    return f"AgentCoreRuntime-{name}"


def aws_issuer() -> str:
    """The account's AWS token issuer. It exists only with outbound web identity federation on."""
    try:
        info = iam.get_outbound_web_identity_federation_info()
    except ClientError as e:
        sys.exit(f"Outbound web identity federation looks off for account {ACCOUNT} ({e.response['Error']['Code']}).\n"
                 "Turn it on in IAM (Account settings), then run this again.")
    if not info.get("JwtVendingEnabled"):
        sys.exit(f"Outbound web identity federation is off for account {ACCOUNT}. Turn it on in IAM first.")
    return info["IssuerIdentifier"]


def setup() -> None:
    hf_issuer = setting("HIGHFLAME_ISSUER_URL")
    issuer = aws_issuer()
    try:
        control.create_oauth2_credential_provider(
            name=PROVIDER,
            credentialProviderVendor="CustomOauth2",
            oauth2ProviderConfigInput={"customOauth2ProviderConfig": {
                "oauthDiscovery": {"discoveryUrl": f"{hf_issuer}/.well-known/openid-configuration"},
                # The account's AWS issuer, not one role: Highflame picks the agent from the role
                # in each token, so this one provider serves every runtime in the account.
                "clientId": issuer,
                "clientAuthenticationMethod": "AWS_IAM_ID_TOKEN_JWT",
            }})
        print(f"Created credential provider {PROVIDER}.")
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("ConflictException", "ValidationException") or "exist" not in str(e):
            raise
        print(f"Credential provider {PROVIDER} already exists.")

    s3 = session.client("s3")
    bucket = code_bucket()
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
        s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
        print(f"Created code bucket {bucket}.")
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou",):
            raise
        print(f"Code bucket {bucket} already exists.")

    print("\nIn Highflame, as the organization's owner, add this workload issuer and verify it:")
    print(f"  Issuer URL: {issuer}")
    print(f"  Audiences:  {hf_issuer}")
    print(f"              {hf_issuer}/oauth2/token   (AgentCore Identity puts this one in its tokens)")


def build_zip(name: str) -> pathlib.Path:
    """The agent's code and its packages for Linux ARM64, as one zip."""
    out = BUILD_DIR / name
    shutil.rmtree(out, ignore_errors=True)
    (out / "pkg").mkdir(parents=True)
    req = str(AGENT_DIR / "requirements.txt")
    if shutil.which("uv"):
        cmd = ["uv", "pip", "install", "--quiet", "--target", str(out / "pkg"), "--python-platform",
               "aarch64-manylinux2014", "--python-version", RUNTIME_PYTHON, "--only-binary", ":all:", "-r", req]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--target", str(out / "pkg"), "--platform",
               "manylinux2014_aarch64", "--python-version", RUNTIME_PYTHON, "--implementation", "cp",
               "--only-binary=:all:", "-r", req]
    subprocess.run(cmd, check=True)
    archive = out / "code.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted((out / "pkg").rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                z.write(path, path.relative_to(out / "pkg"))
        for path in sorted(AGENT_DIR.glob("*.py")):
            z.write(path, path.name)
    print(f"Built {archive} ({archive.stat().st_size // 1024} KiB).")
    return archive


def ensure_role(name: str) -> str:
    """The runtime's own execution role. Only AgentCore can assume it, so Highflame can link it."""
    trust = {"Version": "2012-10-17", "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
        "Action": "sts:AssumeRole",
        "Condition": {"StringEquals": {"aws:SourceAccount": ACCOUNT}},
    }]}
    arn_prefix = f"arn:aws:bedrock-agentcore:{REGION}:{ACCOUNT}"
    policy = {"Version": "2012-10-17", "Statement": [
        {"Sid": "HighflameTokenFromAgentCoreIdentity", "Effect": "Allow",
         "Action": ["bedrock-agentcore:GetWorkloadAccessToken", "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                    "bedrock-agentcore:GetWorkloadAccessTokenForUserId", "bedrock-agentcore:GetResourceOauth2Token"],
         "Resource": [f"{arn_prefix}:workload-identity-directory/default",
                      f"{arn_prefix}:workload-identity-directory/default/workload-identity/*",
                      f"{arn_prefix}:token-vault/default",
                      f"{arn_prefix}:token-vault/default/oauth2credentialprovider/{PROVIDER}"]},
        {"Sid": "AwsRoleTokenForHighflame", "Effect": "Allow",
         "Action": "sts:GetWebIdentityToken", "Resource": "*"},
        {"Sid": "BedrockThroughTheGateway", "Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:CallWithBearerToken"],
         "Resource": "*"},
        {"Sid": "Logs", "Effect": "Allow",
         "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents",
                    "logs:DescribeLogStreams", "logs:DescribeLogGroups"],
         "Resource": f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/aws/bedrock-agentcore/runtimes/*"},
        {"Sid": "Code", "Effect": "Allow", "Action": "s3:GetObject",
         "Resource": f"arn:aws:s3:::{code_bucket()}/{name}/*"},
    ]}
    role = role_name(name)
    try:
        arn = iam.create_role(RoleName=role, AssumeRolePolicyDocument=json.dumps(trust),
                              Description=f"Execution role of the AgentCore runtime {name} (Highflame recipe)")["Role"]["Arn"]
        print(f"Created role {role}.")
    except ClientError as e:
        if e.response["Error"]["Code"] != "EntityAlreadyExists":
            raise
        arn = iam.get_role(RoleName=role)["Role"]["Arn"]
        print(f"Role {role} already exists.")
    iam.put_role_policy(RoleName=role, PolicyName="agentcore-runtime", PolicyDocument=json.dumps(policy))
    return arn


def runtime_by_name(name: str) -> dict | None:
    token = None
    while True:
        page = control.list_agent_runtimes(**({"nextToken": token} if token else {}))
        for rt in page.get("agentRuntimes", []):
            if rt["agentRuntimeName"] == name:
                return rt
        token = page.get("nextToken")
        if not token:
            return None


def deploy(name: str) -> None:
    env = {
        "HIGHFLAME_LLM_URL": setting("HIGHFLAME_LLM_URL"),
        "HIGHFLAME_PROVIDER": PROVIDER,
        "HIGHFLAME_SCOPES": os.environ.get("HIGHFLAME_SCOPES", ""),
        "BEDROCK_MODEL_ID": os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6"),
    }
    archive = build_zip(name)
    key = f"{name}/code-{int(time.time())}.zip"
    session.client("s3").upload_file(str(archive), code_bucket(), key)
    role_arn = ensure_role(name)
    time.sleep(10)  # a new role takes a few seconds before AgentCore can assume it
    artifact = {"codeConfiguration": {"code": {"s3": {"bucket": code_bucket(), "prefix": key}},
                                      "runtime": "PYTHON_" + RUNTIME_PYTHON.replace(".", "_"),
                                      "entryPoint": ["agent_app.py"]}}
    existing = runtime_by_name(name)
    if existing:
        control.update_agent_runtime(agentRuntimeId=existing["agentRuntimeId"], agentRuntimeArtifact=artifact,
                                     roleArn=role_arn, networkConfiguration={"networkMode": "PUBLIC"},
                                     environmentVariables=env)
        runtime_id = existing["agentRuntimeId"]
        print(f"Updating runtime {name}.")
    else:
        runtime_id = control.create_agent_runtime(
            agentRuntimeName=name, agentRuntimeArtifact=artifact, roleArn=role_arn,
            networkConfiguration={"networkMode": "PUBLIC"}, environmentVariables=env,
            tags={"highflame-recipe": "agentcore-config-only"})["agentRuntimeId"]
        print(f"Creating runtime {name}.")
    while True:
        rt = control.get_agent_runtime(agentRuntimeId=runtime_id)
        if rt["status"] in ("READY", "CREATE_FAILED", "UPDATE_FAILED"):
            break
        time.sleep(10)
    print(f"Runtime {name}: {rt['status']} {rt.get('failureReason', '')}".rstrip())
    print(f"  runtime ARN:        {rt['agentRuntimeArn']}")
    print(f"  execution role ARN: {role_arn}   (Highflame links this role to the agent)")


def invoke(name: str, prompt: str) -> dict:
    rt = runtime_by_name(name)
    if not rt:
        sys.exit(f"No runtime named {name}.")
    # With SigV4 inbound auth, AgentCore hands the agent a workload access token (which
    # AgentCore Identity needs) only when the caller names a runtime user. That user is the
    # caller's, not Highflame's: the agent's Highflame token names the agent either way.
    data = session.client("bedrock-agentcore").invoke_agent_runtime(
        agentRuntimeArn=rt["agentRuntimeArn"], runtimeSessionId=f"{uuid.uuid4()}{uuid.uuid4()}"[:48],
        runtimeUserId=os.environ.get("RUNTIME_USER_ID", "recipe-operator"),
        payload=json.dumps({"prompt": prompt}).encode())
    body = data["response"].read().decode()
    try:
        return json.loads(body)
    except ValueError:
        return {"error": f"not JSON: {body[:300]}"}


def destroy(name: str) -> None:
    rt = runtime_by_name(name)
    if rt:
        control.delete_agent_runtime(agentRuntimeId=rt["agentRuntimeId"])
        print(f"Deleting runtime {name}.")
    role = role_name(name)
    try:
        iam.delete_role_policy(RoleName=role, PolicyName="agentcore-runtime")
        iam.delete_role(RoleName=role)
        print(f"Deleted role {role}.")
    except ClientError as e:
        print(f"Role {role}: {e.response['Error']['Code']}")


def teardown() -> None:
    try:
        control.delete_oauth2_credential_provider(name=PROVIDER)
        print(f"Deleted credential provider {PROVIDER}.")
    except ClientError as e:
        print(f"Credential provider {PROVIDER}: {e.response['Error']['Code']}")
    bucket = session.resource("s3").Bucket(code_bucket())
    try:
        bucket.objects.all().delete()
        bucket.delete()
        print(f"Deleted code bucket {code_bucket()}.")
    except ClientError as e:
        print(f"Code bucket: {e.response['Error']['Code']}")


if __name__ == "__main__":
    command, args = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if command == "setup":
        setup()
    elif command == "deploy" and len(args) == 1:
        deploy(args[0])
    elif command == "invoke" and len(args) == 2:
        print(json.dumps(invoke(args[0], args[1]), indent=2))
    elif command == "destroy" and len(args) == 1:
        destroy(args[0])
    elif command == "teardown":
        teardown()
    else:
        sys.exit(__doc__)
