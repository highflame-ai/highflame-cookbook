# Cost Controls for Custom Agents

A custom agent calls its model directly and uses the Highflame SDK for guardrails. To put it under a
per-project budget in US dollars, it reports what each model call used with one SDK call,
`usage.report()`. Highflame prices the call and adds it to the project's spend, and the guard check
the agent already makes refuses the next prompt once the budget is used up, before any more money
is spent.

The agent is registered in the Highflame **Registry** and signs every call with its own API key, so
the spend and the chargeback report name the agent.

Agents whose model calls go through the AI Gateway need no code at all: see
[`../01-ai-gateway/`](../01-ai-gateway/). For the templates and the troubleshooting table, see
[`../README.md`](../README.md).

---

## Set up once in Studio

Use a project that only this notebook uses. When the budget is used up, **every** prompt in the
project is blocked.

1. Sign in at [studio.highflame.ai](https://studio.highflame.ai) and create a project, for example
   `cost-controls-custom-agents`.
2. **Custom Agents → Policies → Cost Controls → Set budget.** Set **Daily budget (USD)** to `0.05`
   and select **Deploy**.
3. In the same tab, deploy the **Daily Budget** template. The deploy dialog starts on **Monitor**;
   set **Enforcement Mode** to **Enforce**.
4. **Registry → Register Identity.** Keep **Agent Identity** on, name the agent (for example
   `Support Summary Agent`), and select **Register Identity**. Copy the API key it shows; Studio
   shows it only once.

```bash
cp .env.example .env      # the agent's key from step 4, and your OpenAI key in PROVIDER_API_KEY
pip install -r requirements.txt
```

Use the agent's key, not an AI Gateway key. The notebook stops at its first cell if the key does
not belong to a registered agent.

---

## Run the proof

```bash
jupyter lab cost_controls_custom_agents.ipynb
```

The committed outputs are a run on studio.highflame.ai:

```
agent  : Support Summary Agent (cost-controls-support-agent, active)
project today: [####................]  21% of $0.05 (~$0.011)     <- call 1, $0.0107
 2  allowed   tokens 3099/385   $0.0116                   [########............]  44% of $0.05 (~$0.022)
 3  allowed   tokens 3099/377   $0.0115                   [#############.......]  67% of $0.05 (~$0.034)
 4  allowed   tokens 3099/359   $0.0113                   [##################..]  90% of $0.05 (~$0.045)
 5  allowed   tokens 3099/400   $0.0117                   [####################] 100% of $0.05 (~$0.050)  USED UP
 6  BLOCKED   tokens -          -                         [####################] 100% of $0.05 (~$0.050)  USED UP

What the agent got back:
  Enterprise Policies Triggered: Daily Budget

By agent
  cost-controls-support-agent  $0.0569    6 calls  100%
```

The dollar amounts are what Highflame priced each call at. Call 5 crossed the budget and completed;
call 6 was refused at the guard check, before the model was called.

`smoke_test.py` reports a $0 call and reads the budget:

```bash
python smoke_test.py
```

---

## Add it to your own agent

Guard the prompt before the model call, as you already do, and report the token counts after it:

```python
from highflame import Highflame

highflame = Highflame(api_key="zid_sk_...")   # the agent's own key, from the Registry

decision = highflame.guard.evaluate_prompt(prompt, session_id=session_id)
if not decision.allowed:
    return decision.policy_reason          # a used-up budget is refused here, before any spend

reply = openai.chat.completions.create(model="gpt-4o", messages=messages)
cached = reply.usage.prompt_tokens_details.cached_tokens or 0
highflame.usage.report(
    model="gpt-4o",
    provider="openai",
    input_tokens=reply.usage.prompt_tokens - cached,   # input excludes cached tokens
    cache_read_tokens=cached,
    output_tokens=reply.usage.completion_tokens,
    session_id=session_id,
)
```

Report each model call once. `usage.report()` returns what Highflame priced the call at
(`cost_micros`, in millionths of a dollar) and whether the model is in the price table (`priced`).
