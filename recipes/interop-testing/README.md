# Interop testing

Runnable clients and servers for the OpenID AIIM CG **MCP Security
Interoperability Event** (Gartner IAM Summit, December 2026).

Tracking issue: highflame-firehog#580. The row-by-row matrix of what we satisfy
lives in `highflame-regression/tests/api/mcp_interop/INTEROP-MATRIX.md`.

| Folder | Standard | What it is |
|---|---|---|
| [`cimd/`](./cimd) | Client ID Metadata Documents, `draft-ietf-oauth-client-id-metadata-document` / MCP SEP-991 | An MCP client that publishes its own document and uses its URL as the `client_id`. |

## How this differs from the regression suite

`highflame-regression` holds the matrix suite. It runs under pytest, against a
harness it stands up itself, and it answers "does our implementation still do
what we say it does".

This folder holds the other half: software a **partner** can point at us, and
software we can point at a **partner**, over the public internet, with no shared
fixture and no repository access. The two must agree, and when they disagree the
transcript here is what settles it.
