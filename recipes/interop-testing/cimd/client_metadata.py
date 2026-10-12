"""Serves this client's Client ID Metadata Document. Nothing else.

CIMD is `draft-ietf-oauth-client-id-metadata-document`, adopted by MCP as
SEP-991. A client publishes a small JSON document at an HTTPS URL, and that URL
*is* its `client_id`. There is no registration, and the authorization server
stores nothing.

This is the only part of the client that must be reachable from the public
internet. The authorization server dereferences the `client_id` URL itself,
from inside its own cluster, so a document on localhost is invisible to it, and
ZeroID's SSRF guard refuses a private address in any case.

Run it, then put a tunnel in front of it:

    ./.venv/bin/python -m uvicorn client_metadata:app --port 8800
    ngrok http 8800

The document's `client_id` is derived from the request, so it self-references
correctly whatever URL the tunnel hands out and you never configure one. Open
the ngrok URL plus /cimd/client.json in a browser to see what the authorization
server will see.

The redirect URI is the one thing it cannot derive, because the notebook picks
that port. They agree on 8765 by default; override with CIMD_REDIRECT_URI.
"""
from __future__ import annotations

import json
import os
import pathlib
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from jwcrypto import jwk
from fastapi.responses import JSONResponse

DOC_PATH = "/cimd/client.json"

# RFC 8252 loopback. The notebook binds this port; this server only declares it.
REDIRECT_URI = os.environ.get("CIMD_REDIRECT_URI", "http://127.0.0.1:8765/callback")
CLIENT_NAME = os.environ.get("CIMD_CLIENT_NAME", "Highflame CIMD interop client")
CLIENT_URI = os.environ.get("CIMD_CLIENT_URI", "https://highflame.ai")
# client_credentials refuses a client registered with no scopes, so the m2m
# variants must declare one. Override to match what the server advertises.
M2M_SCOPE = os.environ.get("CIMD_M2M_SCOPE", "mcp:invoke")
# draft §8.5 names the logo alongside the application name. Settable so a tester
# can also publish a hostile value (javascript:, data:, http:) and confirm the
# authorization server drops it rather than putting it in front of a human.
LOGO_URI = os.environ.get("CIMD_LOGO_URI", "https://highflame.ai/logo.png")

app = FastAPI(title="CIMD metadata origin", docs_url=None, redoc_url=None)

# The signing key for the confidential variants. Generated once and kept on
# disk, because the document publishes the PUBLIC half and the authorization
# server caches a resolved client for an hour: a key that changed per process
# would strand every cached client on a key nobody holds any more.
#
# `.gitignore` covers it. It is a test key for an interop event, not a secret
# worth protecting, but it has no business in a public repository either.
KEY_PATH = pathlib.Path(__file__).parent / "client-signing-key.jwk"


def signing_key() -> "jwk.JWK":
    if KEY_PATH.exists():
        return jwk.JWK.from_json(KEY_PATH.read_text())
    key = jwk.JWK.generate(kty="EC", crv="P-256", kid="highflame-interop-1", alg="ES256", use="sig")
    KEY_PATH.write_text(key.export_private())
    KEY_PATH.chmod(0o600)
    print(f"[key ] generated {KEY_PATH.name} (kid=highflame-interop-1, ES256)")
    return key


def public_jwk() -> dict[str, Any]:
    return json.loads(signing_key().export_public())


# The document variants. Each row is one cell of the CIMD interop matrix, so a
# run can point at exactly the shape it means to exercise rather than editing
# one document between attempts.
#
#   public                 token_endpoint_auth_method=none      the PKCE public-client row
#   confidential-inline    private_key_jwt, key in `jwks`       the "jwks support" row
#   confidential-jwks-uri  private_key_jwt, key at `jwks_uri`   the "jwks_uri support" row
#   m2m-inline             the above plus client_credentials    the "client creds grant" row
#   m2m-jwks-uri           likewise, key by reference
VARIANTS = {
    "public": {"auth": "none", "keys": None, "m2m": False},
    "confidential-inline": {"auth": "private_key_jwt", "keys": "inline", "m2m": False},
    "confidential-jwks-uri": {"auth": "private_key_jwt", "keys": "uri", "m2m": False},
    "m2m-inline": {"auth": "private_key_jwt", "keys": "inline", "m2m": True},
    "m2m-jwks-uri": {"auth": "private_key_jwt", "keys": "uri", "m2m": True},
}

# Every request served, in order. The authorization server's dereference lands
# here, and it is the evidence the CIMD interop row asks for: a fetch from the
# cluster's address with a Go user agent. The notebook reads it from /fetches
# rather than importing this module.
FETCHES: list[dict[str, Any]] = []


def public_url(request: Request, path: str) -> str:
    """The URL this request arrived on, as the caller saw it.

    Deriving `client_id` from the request is what makes this server
    zero-configuration behind a tunnel whose hostname changes every run. ngrok
    sets `X-Forwarded-Proto: https`, and Starlette already folds
    `X-Forwarded-Host` into `request.url` where a proxy sets it.
    """
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{scheme}://{host}{path}"


def document(client_id: str, variant: str, jwks_url: str) -> dict[str, Any]:
    """The published document.

    Three fields are load-bearing.

    `client_id` names this document's own URL. The draft requires that
    self-reference (section 4) and ZeroID enforces it, because without it anyone
    could point a `client_id` at someone else's document and inherit their
    redirect URIs.

    `redirect_uris` holds the loopback URI the client listens on. The
    authorization server validates the requested `redirect_uri` against this
    list, with RFC 8252 loopback matching, so `127.0.0.1.evil.com` is not a
    loopback.

    `token_endpoint_auth_method` is `none`, which is not a shortcut. A CIMD
    client never registers, so there is no channel over which a secret could
    have been issued to it. Public client plus PKCE is the shape MCP 2025-11-25
    prefers.

    There is deliberately NO `scope`. A client cannot know what a server will
    ask for until it has read that server's metadata, and declaring one here
    caps what this client can ever be granted: ZeroID builds the ephemeral
    client's ceiling from this field and intersects it against whatever is
    requested, so a document declaring `a b` against a server advertising `c d`
    fails with `invalid_scope` naming the identity rather than the real cause.
    An absent `scope` means no client-side ceiling. Let discovery decide.
    """
    spec = VARIANTS[variant]
    doc: dict[str, Any] = {
        "client_id": client_id,
        "client_name": f"{CLIENT_NAME} ({variant})",
        "client_uri": CLIENT_URI,
        "logo_uri": LOGO_URI,
        "redirect_uris": [REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": spec["auth"],
    }

    if spec["auth"] == "private_key_jwt":
        # RFC 7523 section 2.2. The server verifies the assertion against
        # whichever of these two the document publishes, so the pair of
        # variants is what separates the `jwks` row from the `jwks_uri` row.
        doc["token_endpoint_auth_signing_alg"] = "ES256"
        if spec["keys"] == "inline":
            doc["jwks"] = {"keys": [public_jwk()]}
        else:
            # Must be on the client_id's OWN host: a document cannot borrow
            # someone else's key set.
            doc["jwks_uri"] = jwks_url

    if spec["m2m"]:
        doc["grant_types"] = [*doc["grant_types"], "client_credentials"]
        # The ONE place this client declares a scope, and only because
        # client_credentials refuses a client that carries none: the registered
        # scope set IS the whole authority ceiling there, so an empty one can
        # mint nothing. Every other variant stays scope-free for the reason
        # above.
        doc["scope"] = M2M_SCOPE

    return doc


# Any name under /cimd/ serves the same document, self-referencing whatever URL
# it was asked for. ZeroID caches a resolved CIMD client for an hour keyed by
# client_id, so re-testing a changed document needs a NEW path; without this you
# would wait out the TTL or restart the authorization server.
@app.get("/cimd/{run}/{variant}.json")
async def serve_variant(run: str, variant: str, request: Request) -> JSONResponse:
    if variant not in VARIANTS:
        raise HTTPException(404, f"unknown variant {variant!r}; try one of {sorted(VARIANTS)}")
    return _serve(request, f"/cimd/{run}/{variant}.json", variant)


@app.get("/cimd/{name}.json")
async def serve_document(name: str, request: Request) -> JSONResponse:
    """The original single-segment path. Serves the public variant."""
    return _serve(request, f"/cimd/{name}.json", "public")


@app.get("/jwks.json")
async def serve_jwks(request: Request) -> JSONResponse:
    """The key set the `*-jwks-uri` variants point at."""
    _record(request, "/jwks.json", "")
    return JSONResponse({"keys": [public_jwk()]}, headers=_HEADERS)


_HEADERS = {
    "Cache-Control": "no-store",
    # ngrok's free plan shows a browser interstitial for anything that looks
    # like a browser. This opts out, so a human checking the URL by hand sees
    # the same bytes the authorization server sees.
    "ngrok-skip-browser-warning": "true",
}


def _record(request: Request, path: str, served: str) -> None:
    record = {
        "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "path": path,
        "client": request.headers.get("x-forwarded-for") or (request.client.host if request.client else ""),
        "user_agent": request.headers.get("user-agent", ""),
        "client_id_served": served,
    }
    FETCHES.append(record)
    print(f"[doc ] 200 {path}  from {record['client']}  ua={record['user_agent']!r}")


def _serve(request: Request, doc_path: str, variant: str) -> JSONResponse:
    client_id = public_url(request, doc_path)
    _record(request, doc_path, client_id)
    return JSONResponse(
        document(client_id, variant, public_url(request, "/jwks.json")),
        headers=_HEADERS,
    )


@app.get("/fetches")
async def list_fetches() -> dict[str, Any]:
    """Everything this origin has served. Local use only; never tunnelled traffic."""
    return {"count": len(FETCHES), "fetches": FETCHES}


@app.get("/")
async def index(request: Request) -> dict[str, Any]:
    return {
        "variants": {v: public_url(request, f"/cimd/run1/{v}.json") for v in VARIANTS},
        "jwks_uri": public_url(request, "/jwks.json"),
        "fetches": "/fetches",
        "redirect_uri": REDIRECT_URI,
        "note": "any {run} segment serves the same documents; vary it to dodge the server-side 1-hour cache",
    }
