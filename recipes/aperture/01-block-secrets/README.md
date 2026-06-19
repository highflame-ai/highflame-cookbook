# 01 · Block a credential leak — Claude Code behind Tailscale Aperture

**Customer value:** *"Our developers are productive with Claude Code, but one pasted AWS
key in a prompt is a breach. We want that stopped at the network edge, with our identity
on it, before it ever reaches a model provider."*

**Integration:** [Tailscale **Aperture**](https://tailscale.com/docs/aperture) routes the
tailnet's LLM traffic. Highflame plugs in as an Aperture **`pre_request` hook** → Cerberus
→ Shield. On a secret, Shield denies and Cerberus returns
`{"action":"block","message":"Highflame Security has blocked your prompt because it
violated Enterprise Policy"}` — Aperture surfaces that to the developer in Claude Code.

**What fires:** Shield's `secrets` detector (16+ credential types) flags the AWS key → a
Cedar `forbid` with your `@reject_message` → `deny` → Cerberus `block`.

**Stage:** [`highflame-demo-vault/deploy.sh`](https://github.com/highflame-ai/highflame-demo-vault/blob/main/deploy.sh) (planted AWS example keys).

---

## Track A — wire it up in Studio (the admin's path)

This is the [Tailscale Aperture setup](https://docs.highflame.ai/integrations/tailscale/setup-guide),
condensed:

1. **Studio → Code Agents → Getting Started → click the *Tailscale Aperture* card → Generate API key.**
   ![Tailscale Aperture card](img/01-aperture-card.png)
2. In **Aperture settings** (`http://ai/ui/`), add the Highflame hook:
   ```json
   "hooks": {
     "highflame": {
       "url": "https://api.highflame.ai/v1/cerberus/agent/events",
       "apikey": "<HIGHFLAME_API_KEY>",
       "timeout": "30s",
       "fail_policy": "fail_open"
     }
   }
   ```
3. Add a **sync `pre_request`** grant so Highflame can block before the provider call:
   ```json
   "send_hooks": [
     { "name": "highflame", "events": ["pre_request"], "send": ["user_message", "request_body", "tools"] }
   ]
   ```
4. **Author the policy in Studio:** a guardrail on the `secrets` detector, `forbid`,
   mode `enforce`, with `@reject_message("Highflame Security has blocked your prompt
   because it violated Enterprise Policy")`. The message you write here is exactly what
   the developer sees.
   ![Block-secrets policy](img/02-block-secrets-policy.png)

> Monitor vs enforce is **your Shield policy's** call, not Aperture's — monitor logs a
> would-block and still returns `allow`; enforce returns `block`. Start in monitor,
> promote to enforce, no Aperture change needed.

---

## Track B — see the decision (the engineer's proof)

You don't need a tailnet to prove the hook works — send the exact payload Aperture sends:

```bash
cp .env.example .env        # set HIGHFLAME_API_KEY (the Aperture service key)
pip install -r requirements.txt
python aperture_event.py
```

```text
Aperture hook -> https://api.highflame.ai/v1/cerberus/agent/events

{
  "action": "block",
  "status_code": 403,
  "message": "Highflame Security has blocked your prompt because it violated Enterprise Policy"
}

Highflame Security blocked the request -> 'Highflame Security has blocked your prompt because it violated Enterprise Policy'
```

That `message` is what Aperture relays into Claude Code — branded, specific, not a
generic error.

---

## Verify against prod

```bash
python smoke_test.py
```

Asserts the leak is blocked. This is what the cookbook's scheduled CI runs against a
canary tenant.

---

## Notes & honesty

- **`HIGHFLAME_API_KEY` here is the Aperture service key** from Studio → Code Agents →
  Tailscale Aperture — *not* a gateway/provider key. No key → the scripts skip, not fail.
- **The block-secrets policy must be active** (Track A) and a tenant **Overwatch
  baseline-permit** must be loaded, or Cedar default-deny makes *everything* a block. The
  smoke test `WARN`s rather than lies if the decision isn't what a real policy would give.
- **Identity is the Tailscale differentiator:** every hook payload carries `login_name`
  and `tailnet_name`, so the block is attributed to a real developer on a real node —
  surfaced in Studio → Code Agents. That's the per-agent-identity story auth alone can't tell.
- **Credentials are fake:** AWS's documented `AKIAIOSFODNN7EXAMPLE` / `…EXAMPLEKEY`. They
  match the detector without being real keys (and dodge GitHub push-protection).
