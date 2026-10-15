"""Flow 1: the agent exchanges the person's ID token for a Highflame token.

The agent signed the person in to its own Okta app (signin.py). It presents the
person's ID token to Highflame in an OAuth 2.0 token exchange (RFC 8693) and
signs the request with its delegation key. Highflame issues a token for the
person, with the agent named in `act`, bound to one MCP server. The agent then
calls that server through the Highflame gateway.

    python id_token_flow.py
"""

from __future__ import annotations

import sys

from highflame.zeroid import ZeroIDError

from common import (agent_private_key, fresh_id_token, highflame_tokens, list_mcp_tools,
                    mcp_server_url, scope, setting, show_claims)


def main() -> int:
    id_token = fresh_id_token()
    show_claims("1. The person's ID token, from Okta", id_token,
                ["iss", "sub", "aud", "email", "email_verified"])

    try:
        token = highflame_tokens().exchange_id_token(
            id_token,
            # The ID token's aud: the agent's app in Okta, linked to the agent in Studio.
            client_id=setting("OKTA_CLIENT_ID"),
            private_key_pem=agent_private_key(),
            scope=scope(),
            resource=mcp_server_url(),
        )
    except ZeroIDError as e:
        print(f"\nHighflame refused the exchange ({e.status} {e.code}): {e.message}")
        return 1

    show_claims("2. The Highflame token: for the person, with the agent in act", token.access_token,
                ["sub", "principal_type", "act.sub", "aud", "scope", "user_idp_iss", "user_idp_sub"])

    tools = list_mcp_tools(mcp_server_url(), token.access_token)
    print(f"\n3. tools/list through the Highflame gateway: {len(tools)} tools {tools[:5]}")
    return 0 if tools else 1


if __name__ == "__main__":
    sys.exit(main())
