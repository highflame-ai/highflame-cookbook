"""Flow 2: Okta issues the agent an ID-JAG, and the agent redeems it at Highflame.

With Okta Cross App Access, Okta decides whether the agent may act for the
person at Highflame. The agent asks Okta's token endpoint for an Identity
Assertion JWT Authorization Grant (ID-JAG) addressed to Highflame. It then
redeems the ID-JAG at Highflame with the JWT bearer grant (RFC 7523), signed
with its delegation key, and calls an MCP server through the Highflame gateway.

    python id_jag_flow.py                       # Okta gets the person's ID token
    python id_jag_flow.py --from-refresh-token  # Okta gets the person's refresh token
"""

from __future__ import annotations

import argparse
import sys

from highflame.zeroid import ZeroIDError

from common import (agent_private_key, fresh_id_token, highflame_issuer, highflame_tokens,
                    list_mcp_tools, mcp_server_url, okta_error, okta_token_request, read_token,
                    scope, setting, show_claims)

TOKEN_TYPE = "urn:ietf:params:oauth:token-type:"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-refresh-token", action="store_true",
                        help="give Okta the person's refresh token instead of their ID token")
    args = parser.parse_args()

    # 1. Ask Okta for an ID-JAG for the person, addressed to Highflame's issuer.
    if args.from_refresh_token:
        subject, subject_type = read_token("refresh_token"), TOKEN_TYPE + "refresh_token"
        if not subject:
            sys.exit("No refresh token yet: run `python signin.py` first.")
    else:
        subject, subject_type = fresh_id_token(), TOKEN_TYPE + "id_token"
    resp = okta_token_request({
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "requested_token_type": TOKEN_TYPE + "id-jag",
        "subject_token": subject,
        "subject_token_type": subject_type,
        "audience": highflame_issuer(),
        "scope": scope(),
    })
    if resp.is_error:
        print(f"Okta refused the ID-JAG request ({okta_error(resp)})")
        return 1
    id_jag = resp.json()["access_token"]
    jag = show_claims("1. The ID-JAG, from Okta", id_jag,
                      ["iss", "aud", "sub", "email", "client_id", "act.sub", "scope", "resource"])

    # 2. Redeem it at Highflame. The agent authenticates as the client Okta named
    #    in the ID-JAG. Okta adds no resource claim unless its connection to
    #    Highflame sets a resource identifier, so the agent names the MCP server
    #    it will call, and Highflame binds the token to it.
    try:
        token = highflame_tokens().redeem_id_jag(
            id_jag,
            client_id=jag.get("client_id") or setting("OKTA_CLIENT_ID"),
            private_key_pem=agent_private_key(),
            resource=mcp_server_url(),
        )
    except ZeroIDError as e:
        print(f"\nHighflame refused the ID-JAG ({e.status} {e.code}): {e.message}")
        return 1

    show_claims("2. The Highflame token: for the person, with the agent in act", token.access_token,
                ["sub", "principal_type", "act.sub", "aud", "scope", "user_idp_iss", "user_idp_sub"])

    tools = list_mcp_tools(mcp_server_url(), token.access_token)
    print(f"\n3. tools/list through the Highflame gateway: {len(tools)} tools {tools[:5]}")
    return 0 if tools else 1


if __name__ == "__main__":
    sys.exit(main())
