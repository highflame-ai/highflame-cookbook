"""Sign a person in to the agent's Okta app: the agent's ordinary OpenID Connect sign-in.

Opens Okta's sign-in page in your browser, waits for the redirect on
OKTA_REDIRECT_URI, and redeems the code (authorization code flow with PKCE).
The person's ID token and refresh token are saved to .tokens/ for the two flows.

Nothing here is specific to Highflame. If your agent already signs people in,
it already has these tokens: the two flows show what to do with them.

    python signin.py
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from common import claims, okta_error, okta_metadata, okta_token_request, save_tokens, setting, show_claims

# offline_access asks Okta for a refresh token, so the agent can get a new ID
# token later without another sign-in. email lets Highflame link the person by
# their email the first time it sees them.
SIGNIN_SCOPE = "openid email profile offline_access"


def main() -> int:
    redirect_uri = setting("OKTA_REDIRECT_URI", "http://localhost:8765/callback")
    callback = urlparse(redirect_uri)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state, nonce = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    authorize_url = okta_metadata()["authorization_endpoint"] + "?" + urlencode({
        "client_id": setting("OKTA_CLIENT_ID"), "response_type": "code", "scope": SIGNIN_SCOPE,
        "redirect_uri": redirect_uri, "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256"})

    outcome: dict[str, str] = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (http.server's name)
            url = urlparse(self.path)
            if url.path != callback.path:
                self.send_response(404)
                self.end_headers()
                return
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if query.get("state") != state:
                outcome["error"] = "the redirect's state does not match this sign-in"
            elif "error" in query:
                outcome["error"] = f"Okta: {query['error']}: {query.get('error_description', '')}"
            else:
                resp = okta_token_request({"grant_type": "authorization_code", "code": query.get("code", ""),
                                           "redirect_uri": redirect_uri, "code_verifier": verifier})
                if resp.is_error:
                    outcome["error"] = f"Okta refused the code ({okta_error(resp)})"
                elif claims(resp.json()["id_token"]).get("nonce") != nonce:
                    outcome["error"] = "the ID token's nonce does not match this sign-in"
                else:
                    save_tokens(resp.json())
                    outcome["id_token"] = resp.json()["id_token"]
                    outcome["refresh_token"] = "yes" if resp.json().get("refresh_token") else "no"
            text = outcome.get("error", "Signed in. You can close this tab.")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(text.encode())

        def log_message(self, *args) -> None:
            pass

    server = HTTPServer((callback.hostname or "localhost", callback.port or 80), Callback)
    server.timeout = 1
    print(f"Sign in as the person in your browser. If it does not open, go to:\n\n  {authorize_url}\n")
    webbrowser.open(authorize_url)
    deadline = time.time() + 300
    while not outcome and time.time() < deadline:
        server.handle_request()
    server.server_close()

    if "id_token" not in outcome:
        print(f"Sign-in failed: {outcome.get('error', 'no redirect within 5 minutes')}")
        return 1
    show_claims("Signed in. The person's ID token, from Okta:", outcome["id_token"],
                ["iss", "sub", "aud", "email", "email_verified"])
    print(f"  refresh token    {outcome['refresh_token']}")
    print("\nSaved to .tokens/. Next: python id_token_flow.py, or python id_jag_flow.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
