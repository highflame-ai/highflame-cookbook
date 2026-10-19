"""A Strands agent that acts for the person who calls it, packaged as an Amazon Bedrock AgentCore app.

The caller sends the person's Okta ID token as `Authorization: Bearer`. On AgentCore, the runtime's
JWT authorizer validates it against Okta first, and passes it to this code because `Authorization`
is on the runtime's request header allowlist. On your machine, `python agent_app.py` serves the same
code on http://localhost:8080, and you send the header yourself.

For each call, the agent exchanges the ID token at Highflame twice (RFC 8693), signed with its
delegation key, so that each token is bound to the one place it is used:

- a token for the Highflame MCP gateway: the MCP server's tools, with the person's own connection;
- a token for the Highflame LLM gateway: the model calls, which Highflame records and checks,
  including every tool call the model makes.

Both tokens name the person (`sub`) and the agent (`act`), so every call is recorded for both, and
your gateway policies for the person apply on both paths.

    python agent_app.py     # serves POST /invocations on port 8080
"""

from __future__ import annotations

import os
import pathlib

from aws_bedrock_token_generator import provide_token
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from dotenv import load_dotenv
from highflame.zeroid import ZeroIDClient, ZeroIDError
from strands import Agent
from strands.models.openai import OpenAIModel
from strands.tools.mcp import MCPClient

load_dotenv(pathlib.Path(__file__).resolve().parent / ".env")  # local runs; AgentCore sets env vars

IDENTITY_URL = os.environ["HIGHFLAME_IDENTITY_URL"]
MCP_SERVER_URL = os.environ["MCP_SERVER_URL"]
LLM_GATEWAY_URL = os.environ["HIGHFLAME_LLM_URL"]
OKTA_CLIENT_ID = os.environ["OKTA_CLIENT_ID"]
SCOPE = os.environ.get("SCOPE", "tools:read")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
READ_ONLY_TOOLS = ["notion-search", "notion-fetch", "notion-get-users", "notion-get-teams"]
SYSTEM_PROMPT = "You help the user find things in their Notion workspace. Use the Notion tools to answer."

app = BedrockAgentCoreApp()


def agent_private_key() -> str:
    """The agent's delegation key: from AWS Secrets Manager on AgentCore, from a file locally."""
    secret_id = os.environ.get("AGENT_PRIVATE_KEY_SECRET_ID")
    if secret_id:
        import boto3

        return boto3.client("secretsmanager", region_name=AWS_REGION).get_secret_value(
            SecretId=secret_id)["SecretString"]
    return pathlib.Path(os.environ["AGENT_PRIVATE_KEY_PATH"]).read_text()


def person_token(id_token: str, resource: str) -> str:
    """Exchange the person's ID token for a Highflame token bound to one resource."""
    return ZeroIDClient(base_url=IDENTITY_URL).tokens.exchange_id_token(
        id_token,
        client_id=OKTA_CLIENT_ID,  # the ID token's aud: the agent's Okta app, linked to the agent
        private_key_pem=agent_private_key(),
        scope=SCOPE,
        resource=resource,
    ).access_token


def model(llm_token: str) -> OpenAIModel:
    """Bedrock, through the Highflame LLM gateway.

    The Bedrock API key travels as `Authorization` and is forwarded to Bedrock. The person's
    Highflame token travels in `X-Highflame-Token`, so the two credentials never compete."""
    return OpenAIModel(
        client_args={
            "base_url": LLM_GATEWAY_URL,
            "api_key": provide_token(region=AWS_REGION),  # short-lived, from the AWS credentials
            "default_headers": {"X-Highflame-Token": llm_token},
        },
        model_id=f"bedrock/{BEDROCK_MODEL_ID}",
        params={"max_tokens": 1024, "temperature": 0},
    )


@app.entrypoint
def invoke(payload: dict, context) -> dict:
    """One request from the person: {"prompt": "..."}, with their Okta ID token as the bearer."""
    auth = (getattr(context, "request_headers", None) or {}).get("Authorization", "")
    id_token = auth.removeprefix("Bearer ").strip()
    if not id_token:
        return {"error": "No person: call this agent with the person's Okta ID token as the bearer."}

    try:
        mcp_token = person_token(id_token, MCP_SERVER_URL)
        llm_token = person_token(id_token, LLM_GATEWAY_URL)
    except ZeroIDError as e:
        return {"error": f"Highflame refused the exchange ({e.status} {e.code}): {e.message}"}

    notion = MCPClient(
        url=MCP_SERVER_URL,
        headers={"Authorization": f"Bearer {mcp_token}"},
        tool_filters={"allowed": READ_ONLY_TOOLS},
    )
    notion.start()
    try:
        agent = Agent(model=model(llm_token), tools=notion.list_tools_sync(),
                      system_prompt=SYSTEM_PROMPT, callback_handler=None)
        result = agent(payload.get("prompt", ""))
    finally:
        notion.stop(None, None, None)

    tool_metrics = getattr(getattr(result, "metrics", None), "tool_metrics", {}) or {}
    return {
        "answer": str(result).strip(),
        "tools_called": {name: getattr(m, "call_count", None) for name, m in tool_metrics.items()},
    }


if __name__ == "__main__":
    app.run()
