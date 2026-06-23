# Highflame + Enterprise-Managed Authorization (Okta Cross-App Access)

> **Preview.** MCP Enterprise-Managed Authorization (EMA) is a new, evolving standard. The
> Highflame side is live; registering your IdP is coordinated with us during preview (see
> [Connect your IdP](#2-connect-your-idp-to-highflame)). Concepts and the full reference
> live at [docs.highflame.ai](https://docs.highflame.ai).

Your developers' agents connect to MCP servers through Highflame. Today each user has to run
a separate OAuth consent for every MCP server — repeated prompts, scattered grants, no
central control. **Enterprise-Managed Authorization flips that around: your identity provider
decides which MCP servers each agent may reach, and grants it at single sign-on.** No
per-user OAuth dance, instant revocation when someone leaves, one audit trail.

It works through **[Okta Cross-App Access (XAA)](https://www.okta.com/identity-101/cross-app-access-securing-ai-agent-and-app-to-app-connections/)**
and the IETF **Identity Assertion Authorization Grant (ID-JAG)**. On sign-in your IdP mints
a short-lived ID-JAG; Highflame exchanges it for a scoped, audience-restricted access token;
your agent calls the tool. The ID-JAG never reaches the MCP server — it terminates at
Highflame — and every tool call is still checked against your Highflame policies.

```
Agent ──SSO──▶ Okta (Cross-App Access)
                 │  mints ID-JAG  (typ: oauth-id-jag+jwt, single-use, client-bound)
                 ▼
            Highflame  ──exchanges ID-JAG──▶ short-lived, audience-restricted token
                 │
                 ▼
            MCP server (via Highflame)  ──▶ allow · block · step-up   (your policies)
```

**What you gain:** central, IdP-governed MCP access · zero per-user OAuth prompts · access
that disappears the moment your IdP de-provisions the user · a full audit trail of which
agent reached which server, attributed to a real person.

---

## Set it up

### 1. Turn on Cross-App Access in Okta

In your Okta org (or the [xaa.dev](https://developer.okta.com/blog/2026/01/20/xaa-dev-playground)
playground), enable **Cross-App Access** and configure two apps:

- **Requesting app** — your MCP client (Claude Desktop, Cursor, an internal agent…). Note its
  **client ID**.
- **Resource app** — Highflame, the destination the ID-JAG is minted *for*.

Okta's guides: [Build agent-to-app connections with XAA](https://developer.okta.com/blog/2025/09/03/cross-app-access)
and [Configure Cross App Access](https://help.okta.com/oie/en-us/content/topics/apps/apps-cross-app-access.htm).

### 2. Connect your IdP to Highflame

Highflame accepts your Okta ID-JAGs once your org is registered as an **authorization
provider**. During preview, send us your Okta org **issuer URL** and the **requesting-app
client ID** and we register the trust for you (claim mapping, allowed accounts, audience).

Once registered, **Studio → Connections → Enterprise-Managed Authorization** lists your
provider — issuer, audience, and how its claims map to your Highflame identities — so you can
confirm the trust is live. Reference:
[docs.highflame.ai](https://docs.highflame.ai).

### 3. Point your agent at Highflame

Your MCP client connects to your Highflame MCP endpoint as usual. On first call it discovers
Highflame as the resource, your IdP mints the ID-JAG at sign-in, and Highflame issues the
access token — no consent screen per server.

---

## See it work

`smoke_test.py` confirms your Highflame MCP endpoint advertises Enterprise-Managed
Authorization — i.e. an EMA-capable client will discover it and use the IdP path.

```bash
cp .env.example .env          # set HIGHFLAME_MCP_RESOURCE_URL to your gateway's base URL
pip install -r requirements.txt
python smoke_test.py
```

It fetches the endpoint's **protected-resource metadata**
(`/.well-known/oauth-protected-resource`) and checks that it advertises both your
authorization server and the `enterprise-managed-authorization` extension. With no
`HIGHFLAME_MCP_RESOURCE_URL` set it exits early (skip), so it never runs against a real tenant
by accident.

---

## How it works

- **Your IdP is the decision point.** Okta evaluates *which MCP servers this user's agent may
  reach* and encodes it in the ID-JAG. Highflame honors that decision.
- **The grant is single-use and client-bound.** Highflame rejects a replayed ID-JAG and
  requires the redeeming client to match the one your IdP issued it to, so a stolen grant is
  useless.
- **The token is audience-restricted.** Highflame mints a token scoped to the specific MCP
  resource named in the grant — it can't be replayed against a different server.
- **Your runtime policies still apply.** EMA decides *admission* (which servers); your
  Highflame policies still govern *every tool call* (what each call may do), unchanged.
- **Fail-closed.** If your IdP's user can't be mapped to a Highflame identity, no token is
  issued — an un-governed agent never reaches a tool.

---

## Bonus: discover the agents you already have

Before (or alongside) EMA, **Studio → Connections** can discover the agents and third-party
apps your identity provider has *already* granted — Okta, Microsoft Entra, Google Workspace,
Copilot Studio — into one inventory, so you can see and govern shadow agents you didn't know
were there. Add a connector on the Connections screen; no code required.

---

## Troubleshooting

- **`smoke_test.py` reports the extension is missing** — your endpoint URL may be wrong, or
  EMA isn't enabled on your tenant yet (preview). Confirm the URL is your MCP gateway's base
  (the host that serves `/.well-known/oauth-protected-resource`).
- **Okta mints a token but Highflame rejects it** — usually the requesting-app client ID
  registered with Highflame doesn't match the one minting the grant, or the user has no
  mapped Highflame identity. Both are by design (client-binding + fail-closed). Check
  **Studio → Connections** shows your provider, and reach out if the mapping needs adjusting.
