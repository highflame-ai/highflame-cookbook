"""A Strands agent on Amazon Bedrock AgentCore, governed by Highflame through configuration alone.

This file has no Highflame import and no Highflame client. Everything that connects it to
Highflame is a setting:

- AgentCore Identity gets the agent's Highflame token. Its credential provider (HIGHFLAME_PROVIDER)
  presents a token for this runtime's own AWS execution role, so nothing here holds a Highflame
  secret or key.
- The model client points at the Highflame LLM gateway (HIGHFLAME_LLM_URL) and sends the token in
  one header, X-Highflame-Token. The Bedrock API key stays in Authorization.

The MCP server runs inside the runtime, and the agent calls it directly: no MCP gateway is
configured in Highflame. The LLM gateway still sees every tool call the model asks for, and your
Highflame policies apply to it.
"""

from __future__ import annotations

import os
import pathlib
import sys

from aws_bedrock_token_generator import provide_token
from bedrock_agentcore.identity.auth import requires_access_token
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.models.openai import OpenAIModel
from strands.tools.mcp import MCPClient

LLM_URL = os.environ["HIGHFLAME_LLM_URL"]
PROVIDER = os.environ.get("HIGHFLAME_PROVIDER", "highflame-agents")
SCOPES = os.environ.get("HIGHFLAME_SCOPES", "").split()
REGION = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
CRM_SERVER = str(pathlib.Path(__file__).with_name("acme_crm_server.py"))
SYSTEM_PROMPT = (
    "You help the sales team with the Acme CRM. Use the CRM tools to answer. "
    "If a tool call is refused, say so plainly and do not try another way."
)

app = BedrockAgentCoreApp()


@requires_access_token(provider_name=PROVIDER, scopes=SCOPES, auth_flow="M2M")
def highflame_token(*, access_token: str) -> str:
    """The agent's own Highflame token, from AgentCore Identity."""
    return access_token


def model(token: str) -> OpenAIModel:
    """Bedrock, through the Highflame LLM gateway."""
    return OpenAIModel(
        client_args={
            "base_url": LLM_URL,
            "api_key": provide_token(region=REGION),  # a short-term Bedrock API key from the role
            "default_headers": {"X-Highflame-Token": token},
        },
        model_id=f"bedrock/{MODEL_ID}",
        params={"max_tokens": 1024},
    )


@app.entrypoint
def invoke(payload: dict, context) -> dict:
    """One request: {"prompt": "..."}."""
    try:
        token = highflame_token()
    except Exception as e:  # noqa: BLE001 (AgentCore Identity reports a refusal as an exception)
        return {"error": f"AgentCore Identity got no Highflame token: {e}"}

    crm = MCPClient(lambda: stdio_client(StdioServerParameters(command=sys.executable, args=[CRM_SERVER])))
    with crm:
        agent = Agent(model=model(token), tools=crm.list_tools_sync(), system_prompt=SYSTEM_PROMPT,
                      callback_handler=None)
        try:
            result = agent(payload.get("prompt", ""))
        except Exception as e:  # noqa: BLE001 (a gateway refusal reaches the agent as a model error)
            return {"error": str(e)[:1000]}

    tool_metrics = getattr(getattr(result, "metrics", None), "tool_metrics", {}) or {}
    return {
        "answer": str(result).strip(),
        "tools_called": {name: getattr(m, "call_count", None) for name, m in tool_metrics.items()},
    }


if __name__ == "__main__":
    app.run()
