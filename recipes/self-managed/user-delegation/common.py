"""Settings and helpers shared by the scripts in this recipe.

Tokens are written to .tokens/ (mode 0600) and never printed. The scripts print
token claims only, so you can see who each token is for.
"""

from __future__ import annotations

import functools
import json
import os
import pathlib
import sys
import time
import uuid

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from dotenv import load_dotenv

RECIPE_DIR = pathlib.Path(__file__).resolve().parent
TOKENS_DIR = RECIPE_DIR / ".tokens"
load_dotenv(RECIPE_DIR / ".env")

CLIENT_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

# Highflame accepts a person's ID token for a limited time after Okta issues it
# (10 minutes unless your trusted issuer says otherwise). A saved ID token older
# than this is refreshed before use.
ID_TOKEN_REUSE_SECONDS = 300


def setting(name: str, default: str | None = None) -> str:
    """A required setting, from the environment or .env."""
    value = os.environ.get(name) or default
    if not value:
        sys.exit(f"Set {name} in .env (see .env.example).")
    return value


def scope() -> str:
    return setting("SCOPE", "tools:read")


def mcp_server_url() -> str:
    return setting("MCP_SERVER_URL")


# --- Okta ------------------------------------------------------------------


@functools.cache
def okta_metadata() -> dict:
    """Okta's OpenID discovery document: the endpoints the scripts call."""
    url = setting("OKTA_ORG_URL").rstrip("/") + "/.well-known/openid-configuration"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def okta_token_request(form: dict[str, str]) -> httpx.Response:
    """POST to Okta's token endpoint, authenticated as the agent's Okta app.

    Uses the client authentication the app already has: a client secret
    (OKTA_CLIENT_SECRET, sent with HTTP Basic), or a private key whose public
    key is registered on the app (OKTA_PRIVATE_KEY_PATH, sent as a signed
    client assertion).
    """
    endpoint = okta_metadata()["token_endpoint"]
    client_id = setting("OKTA_CLIENT_ID")
    secret = os.environ.get("OKTA_CLIENT_SECRET")
    if secret:
        return httpx.post(endpoint, data=form, auth=(client_id, secret), timeout=30)

    key = serialization.load_pem_private_key(
        pathlib.Path(setting("OKTA_PRIVATE_KEY_PATH")).read_bytes(), password=None
    )
    now = int(time.time())
    headers = {"kid": os.environ["OKTA_KEY_ID"]} if os.environ.get("OKTA_KEY_ID") else None
    assertion = jwt.encode(
        {"iss": client_id, "sub": client_id, "aud": endpoint,
         "iat": now, "exp": now + 120, "jti": str(uuid.uuid4())},
        key,
        algorithm="ES256" if isinstance(key, ec.EllipticCurvePrivateKey) else "RS256",
        headers=headers,
    )
    return httpx.post(
        endpoint,
        data={**form, "client_id": client_id,
              "client_assertion_type": CLIENT_ASSERTION_TYPE, "client_assertion": assertion},
        timeout=30,
    )


def okta_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return f"{resp.status_code} {body.get('error')}: {body.get('error_description')}"
    except ValueError:
        return f"{resp.status_code} {resp.text[:300]}"


# --- The person's tokens -----------------------------------------------------


def save_tokens(body: dict) -> None:
    """Keep the person's ID token and refresh token, readable by you only."""
    TOKENS_DIR.mkdir(mode=0o700, exist_ok=True)
    for name in ("id_token", "refresh_token"):
        if body.get(name):
            path = TOKENS_DIR / name
            path.write_text(body[name])
            path.chmod(0o600)


def read_token(name: str) -> str | None:
    path = TOKENS_DIR / name
    return path.read_text().strip() if path.exists() else None


def saved_id_token() -> str | None:
    """The person's saved ID token, refreshed with their refresh token when it is too old
    to use. None when there is no usable sign-in: then the person signs in again."""
    id_token = read_token("id_token")
    if id_token and time.time() - claims(id_token).get("iat", 0) < ID_TOKEN_REUSE_SECONDS:
        return id_token
    refresh_token = read_token("refresh_token")
    if not refresh_token:
        return None
    resp = okta_token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})
    if resp.is_error or "id_token" not in resp.json():
        print(f"Okta did not refresh the saved sign-in ({okta_error(resp)}).")
        return None
    save_tokens(resp.json())
    return resp.json()["id_token"]


def fresh_id_token() -> str:
    """The person's ID token, for the scripts: the saved sign-in, else stop."""
    id_token = saved_id_token()
    if not id_token:
        sys.exit("No usable sign-in. Run `python signin.py` first.")
    return id_token


# --- Highflame -----------------------------------------------------------------


def highflame_tokens():
    """The token client of the Highflame SDK, pointed at your deployment."""
    from highflame.zeroid import ZeroIDClient

    client = ZeroIDClient(base_url=setting("HIGHFLAME_IDENTITY_URL"))
    if not hasattr(client.tokens, "redeem_id_jag"):
        sys.exit("This recipe needs a newer Highflame SDK: pip install -U -r requirements.txt")
    return client.tokens


@functools.cache
def highflame_issuer() -> str:
    """Highflame's issuer: the audience Okta must address an ID-JAG to."""
    url = setting("HIGHFLAME_IDENTITY_URL").rstrip("/") + "/.well-known/oauth-authorization-server"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()["issuer"]


def agent_private_key() -> str:
    """The agent's delegation key (EC P-256). Its public half is on the agent in Studio."""
    return pathlib.Path(setting("AGENT_PRIVATE_KEY_PATH")).read_text()


# --- Display and the MCP call ------------------------------------------------------


def claims(token: str) -> dict:
    """A JWT's claims, for display only. The receiver of a token checks its signature."""
    return jwt.decode(token, options={"verify_signature": False})


def show_claims(title: str, token: str, names: list[str]) -> dict:
    c = claims(token)
    print(f"\n{title}")
    for name in names:
        value = c
        for part in name.split("."):
            value = value.get(part, "<absent>") if isinstance(value, dict) else "<absent>"
        print(f"  {name:<16} {value}")
    return c


class McpHttpError(Exception):
    """The gateway or the MCP server refused a request at the HTTP level."""

    def __init__(self, method: str, resp: httpx.Response):
        self.status = resp.status_code
        self.body = resp.headers.get("www-authenticate") or resp.text[:500]
        super().__init__(f"The MCP server answered {self.status} to {method}: {self.body}")


class McpSession:
    """A minimal MCP client (streamable HTTP) that sends a bearer token on every request."""

    def __init__(self, url: str, token: str):
        self.url = url
        self.headers = {"Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                        "Authorization": f"Bearer {token}"}
        self.http = httpx.Client(timeout=60)
        self._next_id = 0
        resp = self._post("initialize", {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "highflame-user-delegation-recipe", "version": "1.0"}})
        if session := resp.headers.get("mcp-session-id"):
            self.headers["Mcp-Session-Id"] = session
        self._post("notifications/initialized", None)

    def _post(self, method: str, params: dict | None) -> httpx.Response:
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if not method.startswith("notifications/"):
            self._next_id += 1
            payload["id"] = self._next_id
        if params is not None:
            payload["params"] = params
        resp = self.http.post(self.url, headers=self.headers, json=payload)
        if resp.is_error:
            raise McpHttpError(method, resp)
        return resp

    @staticmethod
    def _result(resp: httpx.Response) -> dict:
        if resp.headers.get("content-type", "").startswith("text/event-stream"):
            for line in resp.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:]).get("result") or {}
            return {}
        return resp.json().get("result") or {}

    def list_tools(self) -> list[dict]:
        return self._result(self._post("tools/list", {})).get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> tuple[bool, str]:
        """(is_error, the result's text). A gateway policy refusal comes back as is_error."""
        result = self._result(self._post("tools/call", {"name": name, "arguments": arguments}))
        text = " ".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        return bool(result.get("isError")), text

    def close(self) -> None:
        self.http.close()


def list_mcp_tools(url: str, token: str) -> list[str]:
    """initialize, then tools/list, on an MCP server (streamable HTTP) with a bearer token."""
    try:
        session = McpSession(url, token)
        try:
            return [t["name"] for t in session.list_tools()]
        finally:
            session.close()
    except McpHttpError as e:
        sys.exit(str(e))
