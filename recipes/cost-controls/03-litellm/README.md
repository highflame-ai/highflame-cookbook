# Cost Controls in a LiteLLM proxy

A LiteLLM proxy that calls every provider itself can run under a per-project budget in US dollars.
The Highflame guardrail from [`../../litellm/`](../../litellm/) (Mode B) reports each call's token
counts when its config has `report_usage: true`. Highflame prices each call and adds it to the
project's spend, and the guardrail's `pre_call` check refuses the next prompt once the budget is used
up, before any more money is spent. The apps behind the proxy do not change.

Routes that send their calls through the AI Gateway (Mode A) need nothing: see
[`../01-ai-gateway/`](../01-ai-gateway/). The guardrail skips those calls, so they are never counted
twice. For the templates and the troubleshooting table, see [`../README.md`](../README.md).

---

## Set up once in Studio

Use a project that only this notebook uses. When the budget is used up, **every** prompt in the
project is blocked.

1. Sign in at [studio.highflame.ai](https://studio.highflame.ai) and create a project, for example
   `cost-controls-litellm`.
2. **Custom Agents → Policies → Cost Controls → Set budget.** Set **Daily budget (USD)** to `0.05`
   and select **Deploy**.
3. In the same tab, deploy the **Daily Budget** template. The deploy dialog starts on **Monitor**;
   set **Enforcement Mode** to **Enforce**.
4. **Registry → Register Identity.** Keep **Agent Identity** on, name the agent (for example
   `LiteLLM Proxy`), and select **Register Identity**. Copy the API key it shows; Studio shows it
   only once. Any other API key in the project also works, but then the chargeback cannot name the
   proxy.

The template goes on **Custom Agents**, not on the AI Gateway: Highflame evaluates the guardrail's
checks there, as it does for every SDK caller.

```bash
cp .env.example .env      # the key from step 4, and your OpenAI key in PROVIDER_API_KEY
pip install -r requirements.txt
```

You also need Docker. The notebook builds and runs a LiteLLM proxy image.

---

## Run the proof

```bash
jupyter lab cost_controls_litellm.ipynb
```

From a run on studio.highflame.ai:

```
project today: [####................]  21% of $0.05 (~$0.011)     <- call 1, $0.0107
 2  allowed   tokens 3102/400   $0.0118                   [#########...........]  45% of $0.05 (~$0.022)
 3  allowed   tokens 3102/400   $0.0118                   [#############.......]  68% of $0.05 (~$0.034)
 4  allowed   tokens 3102/400   $0.0118                   [##################..]  92% of $0.05 (~$0.046)
 5  allowed   tokens 3102/400   $0.0118                   [####################] 100% of $0.05 (~$0.050)  USED UP
 6  BLOCKED   tokens -          -                         [####################] 100% of $0.05 (~$0.050)  USED UP

What the agent got back:
  HTTP 400: Highflame policy denied this prompt: Enterprise Policies Triggered: Daily Budget
```

The dollar amounts are what Highflame priced each call at, read from the guardrail's log. Call 5
crossed the budget and completed; call 6 was refused at the guardrail's `pre_call` check, before
LiteLLM called OpenAI. The chargeback report then showed $0.0578 over the run's 5 calls, all by
the Registry agent `litellm-proxy` and all `gpt-4o`.

`smoke_test.py` reports a $0 call and reads the budget:

```bash
python smoke_test.py
```

---

## Add it to your own proxy

Use the guardrail module [`mode_b_shield_guardrail.py`](../../litellm/mode_b_shield_guardrail.py)
with `highflame>=0.7.0` in the proxy's image, and add one line to the guardrail:

```yaml
guardrails:
  - guardrail_name: highflame
    litellm_params:
      guardrail: mode_b_shield_guardrail.HighflameGuardrail
      mode: [pre_call, post_call]   # pre_call is the check that refuses a used-up budget
      default_on: true
      report_usage: true            # or HIGHFLAME_REPORT_USAGE=1 in the proxy's environment
```

What the guardrail reports, and what it skips:

- One report per successful call, sent after the client has its answer, so it adds no latency.
  Streamed calls are reported once the stream ends.
- Each report carries LiteLLM's call id, so a repeated report is not counted twice, and LiteLLM's
  session id. Cached input tokens and cache writes are sent apart from fresh input, so each is
  priced at its own rate.
- Skipped: a LiteLLM cache hit and a `mock_response` route, which call no provider, and a route whose
  `api_base` is the Highflame AI Gateway, which reports the call itself. Set `HIGHFLAME_GATEWAY_URL`
  if your gateway is not at `https://gateway.highflame.ai/llm/v1`.
- A failed report is logged and dropped. It never fails the request.
- `HIGHFLAME_LOG_USAGE=1` logs each report: the model, the token counts, LiteLLM's session and call
  ids, and the price Highflame returned.

The spend belongs to the Highflame key the proxy signs with, not to the callers behind the proxy.
For limits per team or per developer, keep using LiteLLM's own per-key budgets beside the project
budget.
