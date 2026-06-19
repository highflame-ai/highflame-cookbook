# 01 · Block a credential leak

**The value:** *"Our developers are productive with Claude Code, but one pasted or
hardcoded API key in a prompt is a breach. We want it stopped at the network edge — with
our identity on it — before it ever reaches a model provider."*

When a request carries a credential, Highflame blocks it and Aperture shows the developer
your branded message in Claude Code:

```json
{ "action": "block", "message": "Highflame Security has blocked your prompt because it violated Enterprise Policy" }
```

Highflame recognizes 16+ credential types (AWS, GitHub, Stripe, and more).

**Try it in the demo app:** ask the agent *"why is the S3 upload failing? check
[`src/config.js`](https://github.com/highflame-ai/highflame-demo-app/blob/main/src/config.js)"* —
the hardcoded AWS key never reaches the model.

---

## Set up the policy in Studio

1. **Studio → Code Agents → Getting Started → the *Tailscale Aperture* card → Generate API
   key**, and add the hook in Aperture (one-time — see [the track setup](../README.md#one-time-setup)).
   ![Tailscale Aperture card](img/01-aperture-card.png)
2. **Policies → New Policy → Guardrail.** Trigger on detected **secrets**; action
   **block**; mode **enforce**; custom message — *"Highflame Security has blocked your
   prompt because it violated Enterprise Policy."* That message is exactly what the
   developer sees.
   ![Block-secrets policy](img/02-block-secrets-policy.png)

> Monitor vs enforce is the policy's setting: monitor records a would-block while still
> allowing the request; enforce returns the block. Start in monitor, promote to enforce
> when ready — no Aperture change needed.

---

## See the decision

You don't need a tailnet — the included script sends the same request Aperture sends and
prints Highflame's decision:

```bash
cp .env.example .env        # set HIGHFLAME_API_KEY (the Aperture service key)
pip install -r requirements.txt
python aperture_event.py
```

```text
{
  "action": "block",
  "status_code": 403,
  "message": "Highflame Security has blocked your prompt because it violated Enterprise Policy"
}
```

That message is what Aperture relays into Claude Code — branded and specific, not a generic error.

## Verify

```bash
python smoke_test.py
```

Confirms the leak is blocked.

---

## Notes

- **The key** is the Aperture service key from Studio → Code Agents → Tailscale Aperture.
  With no key set, the script skips rather than failing.
- **Make sure the policy is active** and your tenant's baseline authorization policy is
  loaded, so normal requests are allowed and only secrets are blocked. The script warns and
  skips its assertion if the policy isn't in place yet.
- **Identity is the Tailscale advantage:** every request carries the developer's login and
  tailnet, so the block is attributed to a real person on a real device — visible in
  Studio → Code Agents.
- **Credentials in the demo are fake** — AWS's documented example values, which match
  detection without being real keys.
