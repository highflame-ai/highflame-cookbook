"""Drive one CIMD flow against an authorization server, and record what happened.

The notebook walks the public authorization-code flow one hop at a time, for
reading. This is the other half: every row of the CIMD interop matrix, driven
headlessly, so a run is repeatable and its transcript is evidence.

    python flows.py --list
    python flows.py code-public        --server https://gw.example/mcp/…/notion
    python flows.py code-confidential  --server … --keys inline
    python flows.py m2m                --as https://auth.example --tenant ACC:PRJ
    python flows.py negatives          --as https://auth.example --tenant ACC:PRJ

`--doc-origin` is the public URL of client_metadata.py (the ngrok URL). Each run
uses a fresh `{run}` path segment, because a resolved CIMD client is cached for
an hour server-side and a changed document would otherwise not be seen.

mTLS is not here. RFC 8705 needs the TLS layer, which this client does not
terminate, and no Highflame surface implements it.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import pathlib
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from datetime import datetime, timezone
from typing import Any

from jwcrypto import jwk, jwt

HERE = pathlib.Path(__file__).parent
KEY_PATH = HERE / "client-signing-key.jwk"
TRANSCRIPTS = HERE / "transcripts"
STEPS: list[dict[str, Any]] = []


# ── plumbing ────────────────────────────────────────────────────────────────

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """The authorization response IS the redirect. Following it loses the code."""

    def redirect_request(self, *_a, **_k):
        return None


OPENER = urllib.request.build_opener(_NoRedirect)


def step(name: str, **fields: Any) -> None:
    STEPS.append({"at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "step": name, **fields})
    detail = " ".join(f"{k}={v}" for k, v in fields.items() if k != "body")
    print(f"  {name:<34} {detail}")


def post_form(url: str, form: dict[str, str]) -> tuple[int, str, dict[str, str]]:
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(form).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with OPENER.open(req, timeout=30) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


def get_json(url: str) -> tuple[int, Any]:
    try:
        with OPENER.open(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def claims_of(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def assertion(client_id: str, audience: str, *, key: jwk.JWK | None = None, lifetime: int = 300) -> str:
    """An RFC 7523 section 2.2 client assertion, signed with the published key."""
    k = key or jwk.JWK.from_json(KEY_PATH.read_text())
    now = int(time.time())
    t = jwt.JWT(
        header={"alg": "ES256", "kid": json.loads(k.export_public())["kid"], "typ": "JWT"},
        claims={"iss": client_id, "sub": client_id, "aud": audience,
                "jti": str(uuid.uuid4()), "iat": now, "exp": now + lifetime},
    )
    t.make_signed_token(k)
    return t.serialize()


# ── discovery ───────────────────────────────────────────────────────────────

def discover(server_url: str) -> tuple[str, dict[str, Any]]:
    """MCP discovery: unauthenticated call -> 401 -> protected resource -> AS."""
    status, body, headers = post_form(server_url, {})
    challenge = headers.get("WWW-Authenticate") or headers.get("www-authenticate", "")
    step("POST <server> (no token)", status=status, www_authenticate=challenge[:110] or "(none)")

    prm_url = server_url.rstrip("/") + "/.well-known/oauth-protected-resource"
    if 'resource_metadata="' in challenge:
        prm_url = challenge.split('resource_metadata="', 1)[1].split('"', 1)[0]
    status, prm = get_json(prm_url)
    step("GET protected-resource metadata", status=status,
         authorization_servers=prm.get("authorization_servers") if isinstance(prm, dict) else "-")
    if not isinstance(prm, dict) or not prm.get("authorization_servers"):
        raise SystemExit("protected-resource metadata carries no authorization_servers")

    issuer = prm["authorization_servers"][0]
    status, meta = get_json(issuer.rstrip("/") + "/.well-known/oauth-authorization-server")
    step("GET authorization-server metadata", status=status,
         auth_methods=meta.get("token_endpoint_auth_methods_supported") if isinstance(meta, dict) else "-",
         cimd=meta.get("client_id_metadata_document_supported") if isinstance(meta, dict) else "-")
    return issuer, meta


# ── the authorization-code leg ──────────────────────────────────────────────

def code_flow(meta: dict[str, Any], client_id: str, *, resource: str, port: int,
              confidential: bool, open_browser: bool, api_key: str | None = None) -> str | None:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    state = secrets.token_hex(8)

    got: dict[str, str] = {}
    ready = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            got.update({k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Received. You can close this tab.")
            ready.set()

        def log_message(self, *_a):
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
              "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
              "resource": resource}
    if api_key:
        # Non-browser principal. POST the same parameters with `api_key`; the
        # authorization response is the 302, which _NoRedirect keeps for us.
        status, body, headers = post_form(meta["authorization_endpoint"], {**params, "api_key": api_key})
        location = headers.get("Location") or headers.get("location") or ""
        returned = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
        step("POST authorize (api_key principal)", status=status,
             code="yes" if "code" in returned else "no",
             error=returned.get("error", [""])[0] or (body[:70] if status >= 400 else ""))
        server.shutdown()
        if "code" not in returned:
            return None
        got = {k: v[0] for k, v in returned.items()}
        ready.set()
    else:
        url = meta["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)
        step("authorize URL built", client_id=client_id.rsplit("/", 1)[-1], pkce="S256")
        if open_browser:
            print(f"\n  Sign in and approve:\n  {url}\n")
            webbrowser.open(url)
        else:
            print(f"\n  Open this and approve:\n  {url}\n")

        if not ready.wait(timeout=300):
            server.shutdown()
            step("callback", status="TIMEOUT")
            return None
        server.shutdown()

    if "code" not in got:
        step("callback", error=got.get("error"), description=str(got.get("error_description"))[:90])
        return None
    if got.get("state") != state:
        raise SystemExit("state mismatch — refusing the response")
    step("callback", code_len=len(got["code"]), state="matched")

    form = {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": redirect_uri,
            "code_verifier": verifier, "client_id": client_id, "resource": resource}
    if confidential:
        form["client_assertion_type"] = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
        form["client_assertion"] = assertion(client_id, meta["token_endpoint"])
    status, body, _ = post_form(meta["token_endpoint"], form)
    return _token_result(status, body, "token exchange")


def _token_result(status: int, body: str, label: str) -> str | None:
    try:
        payload = json.loads(body)
    except ValueError:
        step(label, status=status, body=body[:120])
        return None
    if "access_token" in payload:
        c = claims_of(payload["access_token"])
        step(label, status=status, sub=c.get("sub"), scopes=c.get("scopes"), client_id=c.get("client_id"))
        return payload["access_token"]
    step(label, status=status, error=payload.get("error"), description=str(payload.get("error_description"))[:100])
    return None


# ── flows ───────────────────────────────────────────────────────────────────

def flow_m2m(issuer: str, meta: dict[str, Any], client_id: str, tenant: str, resource: str | None) -> None:
    account, _, project = tenant.partition(":")
    form = {"grant_type": "client_credentials", "client_id": client_id,
            "account_id": account, "project_id": project,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": assertion(client_id, meta["token_endpoint"])}
    if resource:
        form["resource"] = resource
    status, body, _ = post_form(meta["token_endpoint"], form)
    _token_result(status, body, "client_credentials")


def flow_negatives(meta: dict[str, Any], client_id: str, tenant: str) -> None:
    """The refusals. A success proves nothing unless the forgeries fail."""
    account, _, project = tenant.partition(":")
    base = {"grant_type": "client_credentials", "client_id": client_id,
            "account_id": account, "project_id": project,
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"}
    endpoint = meta["token_endpoint"]

    cases: list[tuple[str, dict[str, str]]] = []

    no_assert = dict(base)
    no_assert.pop("client_assertion_type")
    cases.append(("no client_assertion", no_assert))

    cases.append(("wrong aud", {**base, "client_assertion": assertion(client_id, "https://evil.example/token")}))

    attacker = jwk.JWK.generate(kty="EC", crv="P-256", kid="highflame-interop-1", alg="ES256", use="sig")
    cases.append(("attacker key, same kid", {**base, "client_assertion": assertion(client_id, endpoint, key=attacker)}))

    good = assertion(client_id, endpoint)
    head, payload, sig = good.split(".")
    tampered = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    tampered["sub"] = "https://evil.example/x.json"
    swapped = base64.urlsafe_b64encode(json.dumps(tampered, separators=(",", ":")).encode()).rstrip(b"=").decode()
    cases.append(("payload swapped, old signature", {**base, "client_assertion": f"{head}.{swapped}.{sig}"}))

    zeros = base64.urlsafe_b64encode(b"\x00" * 64).rstrip(b"=").decode()
    cases.append(("signature all zeros", {**base, "client_assertion": f"{head}.{payload}.{zeros}"}))

    expired = assertion(client_id, endpoint, lifetime=-60)
    cases.append(("expired assertion", {**base, "client_assertion": expired}))

    for name, form in cases:
        status, body, _ = post_form(endpoint, form)
        try:
            payload_json = json.loads(body)
            detail = f"{payload_json.get('error')}: {str(payload_json.get('error_description'))[:70]}"
        except ValueError:
            detail = body[:80]
        verdict = "REFUSED" if status >= 400 else "*** ACCEPTED — INVESTIGATE ***"
        step(f"negative: {name}", status=status, verdict=verdict, detail=detail)


# ── entry point ─────────────────────────────────────────────────────────────

FLOWS = {
    "code-public": "authorization_code + PKCE, token_endpoint_auth_method=none",
    "code-confidential": "authorization_code + PKCE + private_key_jwt",
    "m2m": "client_credentials + private_key_jwt",
    "negatives": "forged client assertions — every one must be refused",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("flow", nargs="?", choices=sorted(FLOWS))
    ap.add_argument("--list", action="store_true", help="show the flows and exit")
    ap.add_argument("--server", help="MCP endpoint, for discovery")
    ap.add_argument("--as", dest="issuer", help="authorization server, when skipping discovery")
    ap.add_argument("--doc-origin", default="http://127.0.0.1:8800", help="public URL of client_metadata.py")
    ap.add_argument("--keys", choices=["inline", "uri"], default="inline", help="where the document publishes its key")
    ap.add_argument("--tenant", help="ACCOUNT:PROJECT, for client_credentials")
    ap.add_argument("--port", type=int, default=8765, help="loopback callback port")
    ap.add_argument("--run", default=None, help="cache-busting path segment (default: random)")
    ap.add_argument("--no-browser", action="store_true", help="print the authorize URL instead of opening it")
    ap.add_argument("--api-key", help=(
        "LOCAL ONLY. Post this as the `api_key` form field at /oauth2/authorize so the "
        "authorization server resolves a principal without a browser. Highflame's AuthN "
        "wires no interactive sign-in of its own until highflame-authn#273 lands, which "
        "sends an unauthenticated browser GET to Studio. Never needed against a deployment "
        "that has it."))
    args = ap.parse_args()

    if args.list or not args.flow:
        for name, what in FLOWS.items():
            print(f"  {name:<20} {what}")
        print("\n  mTLS is absent: RFC 8705 needs the TLS layer, which this client does not terminate.")
        return

    run = args.run or secrets.token_hex(3)
    variant = {"code-public": "public",
               "code-confidential": f"confidential-{'inline' if args.keys == 'inline' else 'jwks-uri'}",
               "m2m": f"m2m-{'inline' if args.keys == 'inline' else 'jwks-uri'}",
               "negatives": f"m2m-{'inline' if args.keys == 'inline' else 'jwks-uri'}"}[args.flow]
    client_id = f"{args.doc_origin.rstrip('/')}/cimd/{run}/{variant}.json"

    print(f"\nflow      {args.flow}  —  {FLOWS[args.flow]}")
    print(f"client_id {client_id}\n")

    if args.server:
        issuer, meta = discover(args.server)
    elif args.issuer:
        issuer = args.issuer
        status, meta = get_json(issuer.rstrip("/") + "/.well-known/oauth-authorization-server")
        step("GET authorization-server metadata", status=status,
             auth_methods=meta.get("token_endpoint_auth_methods_supported") if isinstance(meta, dict) else "-")
    else:
        raise SystemExit("pass --server (to discover) or --as (to skip discovery)")
    if not isinstance(meta, dict) or "token_endpoint" not in meta:
        raise SystemExit("authorization-server metadata has no token_endpoint")

    if args.flow in {"m2m", "negatives"} and not args.tenant:
        raise SystemExit("--tenant ACCOUNT:PROJECT is required for this flow")

    if args.flow == "code-public":
        code_flow(meta, client_id, resource=args.server or "", port=args.port,
                  confidential=False, open_browser=not args.no_browser, api_key=args.api_key)
    elif args.flow == "code-confidential":
        code_flow(meta, client_id, resource=args.server or "", port=args.port,
                  confidential=True, open_browser=not args.no_browser, api_key=args.api_key)
    elif args.flow == "m2m":
        flow_m2m(issuer, meta, client_id, args.tenant, args.server)
    elif args.flow == "negatives":
        flow_negatives(meta, client_id, args.tenant)

    TRANSCRIPTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out = TRANSCRIPTS / f"{args.flow}-{stamp}.json"
    out.write_text(json.dumps({"flow": args.flow, "client_id": client_id,
                               "authorization_server": issuer, "steps": STEPS}, indent=2))
    print(f"\ntranscript  {out.relative_to(HERE)}")


if __name__ == "__main__":
    main()
