# Agent governance · discover, adopt, and guard an agent from your IdP

**The value:** *"Our teams are spinning up AI agents faster than we can track them.
Each one is a new identity nobody issued, owns, or can revoke. We want to see every
agent, put a real owner on it, and govern what it does — using the identity provider we
already run, not a new silo."*

Highflame connects to the identity provider you already use — **Google Workspace, Okta,
Microsoft Entra, Copilot Studio** — discovers the agents already operating in your org,
and lets you adopt each one into a registry with an accountable human owner. Once an agent
is adopted and has a guardrail, every request it makes is evaluated *before* it reaches a
model or a tool. A request that violates policy is blocked, and the block is attributed to
the agent and its owner:

```json
{ "action": "block", "message": "Highflame Security has blocked this agent's request because it violated Enterprise Policy" }
```

Identity is where governance starts, not where it stops. Okta and Entra can tell you *who*
an agent is and *what it may connect to*. Highflame adds the next layer: *what the agent
actually does at runtime*, and the evidence that it was governed.

---

## Set it up in Studio

Steps 1-4 are one-time setup in [Highflame Studio](https://studio.highflame.ai). Step 5 is
the runnable proof below.

1. **Connect your identity provider.** Studio → Connections → add **Google Workspace**.
   The same flow works for **Okta**, **Microsoft Entra**, and **Copilot Studio** — connect
   the one you run. No code required.
   <!-- screenshot: Studio → Connections → Add Google Workspace -->
2. **Discover.** The connector surfaces the agents already operating in your org —
   including ones nobody registered. Each shows up in the registry as *discovered*, waiting
   to be governed.
   <!-- screenshot: registry Adoption inbox, N agents discovered -->
3. **Adopt.** Bring the agent you want to govern into your registry and assign it an
   accountable **owner**. Adoption is what turns a discovered, ownerless agent into a
   first-class identity you can hold someone responsible for.
   <!-- screenshot: Adopt dialog, assign owner -->
4. **Attach a guardrail.** Studio → Guardrails → Policies → New Policy. Trigger on the
   violation you care about (here, a leaked **secret**); action **block**; mode **enforce**;
   write the message the caller should see. That message is exactly what comes back on the
   block.
   <!-- screenshot: guardrail policy, block + enforce -->

> Monitor vs enforce is the policy's setting: monitor records a would-block while still
> allowing the request; enforce returns the block. Start in monitor, promote to enforce
> when you're ready.

---

## See the decision

The included script sends a representative request from the adopted agent — one that tries
to ship data to an external endpoint using a hardcoded credential — and prints Highflame's
decision:

```bash
cp .env.example .env        # set HIGHFLAME_API_KEY
pip install -r requirements.txt
python governed_agent_request.py
```

```text
{
  "action": "block",
  "status_code": 403,
  "message": "Highflame Security has blocked this agent's request because it violated Enterprise Policy"
}
```

The message — the one you wrote on the guardrail in Studio — is what the caller sees. The
decision is recorded and attributed to the agent and its owner: open **Studio →
Observatory** to see the blocked request in the agent's trace, with the policy that fired.

## Verify

```bash
python smoke_test.py
```

Confirms the agent's policy-violating request is blocked.

---

## Notes

- **The key** is a Highflame service key (Studio → Settings → API Keys), or the
  agent-gateway key shown on the adopted agent in the registry. With no key set, the script
  skips rather than failing.
- **Works with the IdP you already run.** Google Workspace is the example here; the same
  discover-and-adopt flow covers Okta, Microsoft Entra, and Copilot Studio. Highflame
  extends your existing identity provider to agents rather than replacing it.
- **Make sure the guardrail is active** and your tenant's baseline authorization policy is
  loaded, so ordinary requests are allowed and only violations are blocked. The script warns
  and skips its assertion if the guardrail isn't in place yet.
- **Identity is the point.** Because the agent was adopted with an owner, the block isn't an
  anonymous event — it's attributed to a named agent and a named human, visible in Studio →
  Observatory.
- **Credentials in the example are fake** — AWS's documented example values, which match
  detection without being real keys.
