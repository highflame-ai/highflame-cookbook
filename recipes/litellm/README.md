# Highflame + LiteLLM (compose, don't replace)

You already run **LiteLLM**. You like it — it does routing, fallbacks, budgets, retries.
You do **not** want to rip it out to adopt Highflame. Good: you shouldn't have to.

This recipe shows the two honest ways to add Highflame's guardrails, policy enforcement,
and identity/observability to a stack that already has LiteLLM in it — and exactly when
to pick each.

> **Why not "just set LiteLLM's base URL to Highflame"?** Because that makes *us* do the
> routing and turns LiteLLM into a pass-through — i.e. it asks you to replace LiteLLM.
> That's the wrong ask for an existing LiteLLM user. The two modes below keep LiteLLM
> doing its job.

| | **Mode A — Firehog upstream** | **Mode B — Shield guardrail hook** |
| --- | --- | --- |
| **Idea** | Add Highflame's gateway as *one more provider* in your `model_list`. Route the traffic you want secured through it. | Keep LiteLLM calling every provider directly. Add a guardrail that consults Highflame Shield pre/post. |
| **You keep LiteLLM doing** | routing, fallbacks, budgets — across all providers, including the Highflame one | routing, fallbacks, budgets, *and* all provider calls |
| **Highflame sees** | full request/response for routed traffic → enforce + redact + traces + identity | the prompt and the response text → allow/deny/redact |
| **Code** | **zero** — pure LiteLLM config | a small `CustomGuardrail` class (uses the SDK to mint its JWT) |
| **Pick when** | you're happy to send the secured routes through the gateway (recommended default) | you can't/won't reroute provider traffic and only want a policy verdict |

Both satisfy the same goal — *"if LiteLLM's already in use, integrate Shield, that's it."*
Mode A integrates Shield **transparently**; Mode B integrates it as an **explicit hook**.

---

## Prerequisites

```bash
cp .env.example .env      # fill in your keys
pip install -r requirements.txt
```

You need:

- `HIGHFLAME_API_KEY` — your tenant key (`hf_sk_…`). Get it from Studio → Settings → API Keys.
- A provider key you already use, e.g. `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`.

Endpoints default to prod/SaaS:

| Var | Default | What |
| --- | --- | --- |
| `HIGHFLAME_GATEWAY_URL` | `https://gateway.highflame.ai/v1` | Firehog, OpenAI-compatible |
| `HIGHFLAME_BASE_URL` | `https://api.highflame.ai` | Shield/SDK base (guard at `/v1/shield/guard`) |

---

## Mode A — Firehog as an upstream provider

### The one gotcha: double the provider prefix

Firehog routes by a **`{provider}/{model}`** model string and strips the prefix before
calling upstream (e.g. `openai/gpt-4o` → calls OpenAI with `gpt-4o`).

LiteLLM *also* uses a leading `provider/` to pick its transport, and **strips its own
prefix** before sending the body. So if you write `model: openai/gpt-4o`, LiteLLM sends
the body `model: gpt-4o` and Firehog no longer knows the provider.

**Fix: double-prefix.** Write `openai/openai/gpt-4o`:

```
openai/ openai/gpt-4o
└─┬──┘ └────┬───────┘
  │         └─ what LiteLLM puts in the request body → Firehog sees "openai/gpt-4o" ✓
  └─ tells LiteLLM "use the OpenAI-compatible transport to api_base"
```

For Anthropic *through* Firehog: `openai/anthropic/claude-opus-4-8` (LiteLLM speaks
OpenAI to Firehog; Firehog translates to the Anthropic Messages API).

### Two providers in one `model_list` (LiteLLM proxy)

See [`mode_a_litellm_proxy_config.yaml`](mode_a_litellm_proxy_config.yaml). Start it with:

```bash
litellm --config mode_a_litellm_proxy_config.yaml
# your apps now call gpt-4o-secured / claude-secured on localhost:4000,
# LiteLLM routes them through Firehog, Shield enforces inline.
```

### Or the LiteLLM SDK directly

See [`mode_a_firehog_upstream.py`](mode_a_firehog_upstream.py) for a runnable demo that
sends a benign prompt (passes) and a prompt-injection attempt (blocked by policy at the
gateway). Run it:

```bash
python mode_a_firehog_upstream.py
```

The key call:

```python
import litellm, os

resp = litellm.completion(
    model="openai/openai/gpt-4o",                       # double-prefix (see above)
    api_base=os.environ["HIGHFLAME_GATEWAY_URL"],       # https://gateway.highflame.ai/v1
    api_key=os.environ["OPENAI_API_KEY"],               # rides through to OpenAI as the provider key
    extra_headers={"X-Highflame-APIKey": os.environ["HIGHFLAME_API_KEY"]},  # tenant + policy
    messages=[{"role": "user", "content": "Hello!"}],
)
```

A policy **deny** surfaces as an HTTP error from the gateway, which LiteLLM raises as an
exception — the demo catches it and shows the policy reason.

---

## Mode B — Shield as a LiteLLM guardrail hook

When you want LiteLLM to keep making every provider call itself and only ask Highflame
*"is this allowed?"*, register a guardrail. Shield's guard endpoint takes a **JWT**, not a
raw API key — so the hook uses the Highflame SDK, which mints and refreshes the JWT from
your `HIGHFLAME_API_KEY` automatically.

See [`mode_b_shield_guardrail.py`](mode_b_shield_guardrail.py). It defines
`HighflameGuardrail(CustomGuardrail)` with:

- `async_pre_call_hook` → `guard.aevaluate_prompt(..., mode="enforce")` on the user
  prompt; raises to block on `deny`.
- `async_post_call_success_hook` → evaluates the model's response (`content_type="response"`)
  and can block or redact.

Wire it into the LiteLLM proxy:

```yaml
# mode_b_litellm_proxy_config.yaml
guardrails:
  - guardrail_name: highflame
    litellm_params:
      guardrail: mode_b_shield_guardrail.HighflameGuardrail
      mode: pre_call          # and/or post_call
```

…or, for the pure SDK (no proxy), call the same guard inline around your `completion()` —
the file includes a `guarded_completion()` helper that does exactly that.

---

## Verify against prod

```bash
python smoke_test.py
```

Sends a benign and a malicious prompt through Mode A and asserts: benign returns content,
malicious is blocked. This is what this repo's CI runs on a schedule against a canary
tenant — green means the recipe still works against live prod.

---

## Notes & honesty

- **`mode_a_firehog_upstream.py` and `smoke_test.py` need real keys** and reach prod. With
  no keys they exit early with a clear message rather than pretending to pass.
- **Response-side Cedar action.** Shield's actions are `process_prompt`, `call_tool`,
  `read_file`, `write_file`, `connect_server`. Post-call response checks reuse
  `content_type="response"`; tune the action to match the policies you author.
- **Provider coverage.** Firehog's `{provider}/` prefixes (openai, anthropic, azure,
  gemini, groq, mistral, ollama, together, deepseek, …) are listed in its README and
  driven by `providers.json` — add the ones you route.
