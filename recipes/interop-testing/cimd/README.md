# CIMD interop client

An MCP client that identifies itself with a **Client ID Metadata Document**, for
the OpenID AIIM CG MCP Security Interoperability Event (Gartner IAM Summit,
December 2026). Tracking issue: highflame-firehog#580.

CIMD is `draft-ietf-oauth-client-id-metadata-document`, adopted by MCP as
SEP-991. The client publishes a small JSON document at an HTTPS URL, and that
URL is its `client_id`. There is no registration step and the authorization
server stores nothing.

## Three pieces

| | What it is |
|---|---|
| `client_metadata.py` | A FastAPI server that serves the documents and nothing else. The only part that must be reachable from the public internet. |
| `cimd_client.ipynb` | The public authorization-code flow, one hop per cell, for reading. Self-contained: it imports no local module. |
| `flows.py` | Every flow, driven headlessly, writing a transcript. This is what a matrix row is evidenced with. |

### The document variants

One document per row of the CIMD matrix, so a run points at the shape it means
to exercise instead of editing one document between attempts.

| Path | `token_endpoint_auth_method` | Key | Grants |
|---|---|---|---|
| `/cimd/{run}/public.json` | `none` | — | code, refresh |
| `/cimd/{run}/confidential-inline.json` | `private_key_jwt` | inline `jwks` | code, refresh |
| `/cimd/{run}/confidential-jwks-uri.json` | `private_key_jwt` | `jwks_uri` | code, refresh |
| `/cimd/{run}/m2m-inline.json` | `private_key_jwt` | inline `jwks` | + `client_credentials` |
| `/cimd/{run}/m2m-jwks-uri.json` | `private_key_jwt` | `jwks_uri` | + `client_credentials` |

`{run}` is any segment and serves the same documents. Vary it per run: a
resolved CIMD client is cached for an hour server-side, keyed by `client_id`, so
a changed document is otherwise not seen.

The signing key lives in `client-signing-key.jwk`, generated on first use and
gitignored. It persists deliberately — the document publishes the public half,
and a key that rotated per process would strand every cached client.

Only the `m2m-*` variants declare a `scope`, because `client_credentials`
refuses a client that carries none: there the registered scope set is the whole
authority ceiling, so an empty one can mint nothing. The others stay scope-free
on purpose — a client cannot know a server's vocabulary before reading its
metadata, and guessing caps what it can ever be granted.

## Running a flow

```bash
python flows.py --list

# discovery from the MCP endpoint, then the public PKCE flow
python flows.py code-public --server https://gateway/mcp/<slug> --doc-origin https://<tunnel>

# confidential, both key shapes
python flows.py code-confidential --server … --doc-origin … --keys inline
python flows.py code-confidential --server … --doc-origin … --keys uri

# machine-to-machine, no browser
python flows.py m2m --as https://auth.example --doc-origin … --tenant ACCOUNT:PROJECT

# the forgeries, all of which must be refused
python flows.py negatives --as https://auth.example --doc-origin … --tenant ACCOUNT:PROJECT
```

Each run writes `transcripts/<flow>-<timestamp>.json`.

### Two things that will bite

**A CIMD `client_id` must be `https`.** `IsCIMDClientID` requires it, so an
`http://` document is not recognised as CIMD at all and fails as *"unknown or
inactive client_id"*, which reads like a registration problem and is not one.
That is why the document origin needs a tunnel even on a laptop.

**`--api-key` is a local escape hatch, not part of any flow.** Highflame's AuthN
wires no interactive sign-in of its own until highflame-authn#273 lands, which
sends an unauthenticated browser GET to Studio. Until then the authorize leg has
no way to resolve a human, and this posts the `api_key` form field instead.
Against a deployment that has #273, drop the flag and use the browser.

### Reading a `negatives` run honestly

Every case must be refused, but *why* matters. While
highflame-authn#274 is open, `client_credentials` refuses a CIMD client before
it ever verifies an assertion, so all six refuse with the same
`invalid_client: invalid client credentials` and prove nothing about signature
checking. Once #274 lands they should diverge — `client_assertion verification
failed` for the forged keys, `aud does not identify this authorization server`
for the wrong audience. A uniform refusal is the signal that the grant is still
closed.

## Run it

```bash
# once
uv venv .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt
./.venv/bin/python -m ipykernel install --user --name cimd-interop

# terminal 1 — the document
./.venv/bin/python -m uvicorn client_metadata:app --port 8800

# terminal 2 — put it on the internet
ngrok http 8800

# terminal 3 — the client
jupyter lab cimd_client.ipynb      # pick the `cimd-interop` kernel
```

In the notebook set `SERVER_URL` to the MCP endpoint and `DOCUMENT_URL` to the
ngrok URL plus `/cimd/client.json`, then run top to bottom. One cell opens a
browser and waits for you. Run the last cell even if a step failed, so the next
run can bind the callback port.

`client_metadata.py` derives `client_id` from the request, so it self-references
correctly whatever hostname the tunnel hands out and you never configure one.

## Why ngrok

The authorization server dereferences the `client_id` URL itself, from inside
its own cluster. A document on `localhost` is unreachable to it, and ZeroID's
SSRF guard refuses a private address anyway. A deployment with that guard
relaxed is not the deployment a partner tests.

The free ngrok plan allows one agent session.

## Why it exists

The event scores a matrix, and **a tester never fills its own column.** We check
a partner's boxes and a partner checks ours, so running both halves proves
nothing on its own. What it buys is this: when a partner is on the call, the
hour goes on the test and not on our plumbing.

**Nothing in the authorization flow is hand-rolled.** The `mcp` SDK performs
discovery, picks the `client_id`, builds the PKCE challenge and exchanges the
code. The discovery cells make the same calls a second time so you can read
them; they observe, and are not what is under test.

## The document

```json
{
  "client_id": "https://<tunnel>/cimd/client.json",
  "client_name": "Highflame CIMD interop client",
  "client_uri": "https://highflame.ai",
  "redirect_uris": ["http://127.0.0.1:8765/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none"
}
```

**`client_id` names the document's own URL.** The draft requires that
self-reference (section 4) and ZeroID enforces it. Without it, anyone could
point a `client_id` at someone else's document and inherit their redirect URIs.

**The redirect URI is an RFC 8252 loopback address.** It is what desktop MCP
clients use and it needs no registered hostname. The notebook binds that port;
the server only declares it. Override with `CIMD_REDIRECT_URI`.

**`token_endpoint_auth_method` is `none`,** which is not a shortcut. A CIMD
client never registers, so there is no channel over which a secret could have
been issued to it. Public client plus PKCE is the shape MCP 2025-11-25 prefers.

**There is no `scope`, deliberately.** A client cannot know what a server will
ask for before reading that server's metadata. ZeroID builds the ephemeral
client's ceiling from this field and intersects it against whatever is
requested, so a document declaring `a b` against a server advertising `c d`
fails with `invalid_scope` — naming the identity rather than the real cause. An
absent `scope` means no client-side ceiling. Let discovery decide.

## Reading a failure

The notebook says which side broke, because the SDK's error never does. It
collapses any non-2xx whose body is not a JSON-RPC error into
`INTERNAL_ERROR: Server returned an error response`, discarding the status and
the body, so the notebook replays one call with the minted token and prints the
raw response.

A 401 from a Highflame gateway:

| Body | Meaning |
|---|---|
| `jwt_required` | the server is registered; your credential was not accepted |
| `unauthorized`, *Use OAuth 2.0 or API key* | the gateway could not resolve the server **for this caller** |

The second is not a token rejection. A registered server answers `jwt_required`
for any credential, good or junk.

**A missing document fetch is not proof of failure.** ZeroID caches a resolved
CIMD client for an hour, so a second run on the same document URL legitimately
shows none. A minted token against a document-URL `client_id` is the positive
proof. `/fetches` on the metadata server lists every request it served; your own
probe carries a `python-httpx2` agent and the authorization server's carries
`Go-http-client`.

## Known state on our own deployment

Verified 2026-10-04 against `gateway-dev.highflame.dev`:

- Discovery, CIMD negotiation, consent, PKCE and token issuance all **pass**.
  AuthN dereferences the published document and mints a token bound to the
  exact mount URL.
- `studio-dev.highflame.dev` advertises CIMD; `studio.highflame.ai` does not, so
  **run against dev1**.
- `WWW-Authenticate` carries no `scope` parameter — highflame-firehog#676.
- The MCP call itself fails. Firehog resolves the caller's servers by calling
  Admin with the caller's token, and Admin stopped verifying those tokens when
  it became a pure Studio BFF — highflame-firehog#678.
