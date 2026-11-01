# Cost Controls: a per-project AI budget

An agent stuck in a retry loop can spend a month of model budget in an afternoon. Cost Controls
give each Highflame project a daily and a monthly budget in US dollars. Highflame prices every
model call your agents make, adds it to the project's spend, and blocks new prompts once the
budget is used up.

**What you get**

- One budget for the whole project, whether an agent's model calls go through the Highflame AI
  Gateway or straight to the provider.
- Every call priced by Highflame from one price table, the same for every gateway and every SDK.
- New prompts blocked once the budget is used up, until the next day or month (UTC) or until you
  raise the budget.
- A chargeback report: what each agent, user and model spent.

---

## Two notebooks, one for each way an agent reaches its model

| Notebook | Your agent… | What you change |
| --- | --- | --- |
| [`01-ai-gateway/`](01-ai-gateway/) | sends its model calls through the **AI Gateway** | Nothing. The gateway reports every call. |
| [`02-custom-agents/`](02-custom-agents/) | calls its model directly and uses the **Highflame SDK** (Custom Agents) | One `usage.report()` call after each model call, signed with the agent's own key from the Registry. |

Each notebook spends real money on a $0.05 daily budget and watches it stop. With `gpt-4o` each
call costs about one cent, so the sixth call is refused.

**Give each notebook its own project.** A project has one budget, and both paths count against it.
If you run both notebooks in one project, the first one uses up the budget and the second one
starts blocked.

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
template is deployed in **Enforce** mode. The deploy dialog starts on **Monitor**, which only
records.

---

## Good to know

- The price of a call is known only after the model answers, so the call that crosses the budget
  completes and the one after it is blocked. The headroom template keeps that overshoot small.
- A model that is not in Highflame's price table is counted at $0.
- Days and months are UTC. To run a notebook again on the same day, raise the budget in Studio.
- ChatGPT and Claude subscription traffic is paid for by the subscription, so it is not counted.

| Symptom | Cause |
| --- | --- |
| "This project has no daily budget" | The budget was not deployed, or the key belongs to another project. |
| The bar reaches 100% but calls are still allowed | The Daily Budget template is missing, or in Monitor mode. |
| Blocked on the first call | An earlier run used up today's budget. Raise it in Studio. |
| A call shows `(model not priced)` | The model name is not in the price table. Use the provider's model name. |
