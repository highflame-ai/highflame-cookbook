# Cost Controls: a per-project AI budget

An agent stuck in a retry loop can spend a month of model budget in an afternoon. Cost Controls
give each Highflame project a daily and a monthly budget in US dollars. Highflame prices every
model call your agents make, adds it to the project's spend, and blocks new prompts once the
budget is used up.

**What you get**

- One budget for the whole project, whether an agent's model calls go through the Highflame AI
  Gateway or straight to the provider.
- Every call priced by Highflame from one price table, the same for every gateway and every SDK.
- New prompts blocked once the budget is used up, on every path, until the next day or month (UTC)
  or until you raise the budget.
- A chargeback report: what each agent, user and model spent.

| Your agent reaches its model… | What you change |
| --- | --- |
| Through the **AI Gateway** | Nothing. The gateway reports every call. |
| Directly, guarded with the **Highflame SDK** (Custom Agents) | One `usage.report()` call after each model call. |

---

## Set up once in Studio

Use a project that nothing else depends on while you try this. When the budget is used up,
**every** prompt in the project is blocked.

1. Sign in at [studio.highflame.ai](https://studio.highflame.ai) and create a project, for example
   `cost-controls-demo`.
2. In that project, create an API key: **AI Gateway → Settings → API Keys**.
3. **Custom Agents → Policies → Cost Controls → Set budget.** Set **Daily budget (USD)** to `0.05`
   and select **Deploy**. The same budget applies to the AI Gateway.
4. In the same tab, deploy the **Daily Budget** template. The deploy dialog starts on **Monitor**,
   which only records; set **Enforcement Mode** to **Enforce**.
5. **AI Gateway → Policies → Cost Controls**: deploy **Daily Budget** the same way, in **Enforce**.

```bash
cp .env.example .env      # HIGHFLAME_API_KEY from step 2, and your OpenAI key in PROVIDER_API_KEY
pip install -r requirements.txt
```

---

## Run the proof

```bash
jupyter lab cost_controls.ipynb
```

The notebook spends real money on the tiny budget and watches it stop. With `gpt-4o` each call
costs about one cent, so a $0.05 budget runs out in a handful of calls. Calls 1 and 2 take the
budget to 46%; the loop goes on from there:

```
 3  AI Gateway    allowed   tokens 3099/393   reported by the gateway   [#############.......]  69% of $0.05 (~$0.035)
 4  Custom Agent  allowed   tokens 3099/355   $0.0113                   [##################..]  92% of $0.05 (~$0.046)
 5  AI Gateway    allowed   tokens 3099/400   reported by the gateway   [####################] 100% of $0.05 (~$0.050)  USED UP
 6  Custom Agent  BLOCKED   tokens -          -                         [####################] 100% of $0.05 (~$0.050)  USED UP
 7  AI Gateway    BLOCKED   tokens -          -                         [####################] 100% of $0.05 (~$0.050)  USED UP

What the AI Gateway answered:
  Highflame Security: Prompt blocked: this project has used its daily AI budget.

Why the custom agent's prompt was refused:
  Enterprise Policies Triggered: Daily Budget
```

Call 5 crossed the budget and completed; every prompt after it was refused. The notebook then
prints the chargeback report and deactivates the two agents it registered:

```
Today, this project: $0.0578 over 5 calls

By agent
  cost-gateway-638ffe          $0.0352    3 calls  61%
  cost-custom-638ffe           $0.0227    2 calls  39%
```

`smoke_test.py` checks the wiring without spending anything: it reports a $0 call and reads the
budget.

```bash
python smoke_test.py
```

---

## Add it to your own custom agent

Guard the prompt before the model call, as you already do, and report the token counts after it:

```python
from highflame import Highflame

highflame = Highflame(api_key="zid_sk_...")

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

---

## The templates

All four are under **Policies → Cost Controls**, on Custom Agents. The AI Gateway has the first
three.

| Template | Blocks new prompts when… |
| --- | --- |
| **Daily Budget** | the project's daily budget is used up |
| **Monthly Budget** | the project's monthly budget is used up |
| **Monthly Budget Headroom** | 95% of the monthly budget is used (edit the threshold to fit) |
| **Agent Monthly Budget** | one agent has spent $200 this month (attach it to the agent, edit the threshold per agent) |

A template does nothing until the project has the matching budget. A budget does nothing until a
template is deployed in Enforce mode.

---

## Good to know

- The price of a call is known only after the model answers, so the call that crosses the budget
  completes and the one after it is blocked. The headroom template keeps that overshoot small.
- A model that is not in Highflame's price table is counted at $0, and `usage.report()` returns
  `priced: false` for it.
- Days and months are UTC. To run the notebook again on the same day, raise the budget in Studio.
- ChatGPT and Claude subscription traffic is paid for by the subscription, so it is not counted.

| Symptom | Cause |
| --- | --- |
| "This project has no daily budget" | Step 3 was not deployed, or the key belongs to another project. |
| The bar reaches 100% but calls are still allowed | The Daily Budget template is missing, or in Monitor mode, on that path. |
| Blocked on the first call | An earlier run used up today's budget. Raise it in Studio. |
| A call shows `(model not priced)` | The model name is not in the price table. Use the provider's model name. |
