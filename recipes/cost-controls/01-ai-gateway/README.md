# Cost Controls on the AI Gateway

When an agent's model calls go through the Highflame AI Gateway, a per-project budget in US dollars
needs no change to the agent. The gateway reports every call, Highflame prices it and adds it to
the project's spend, and the gateway refuses new prompts once the budget is used up. The agent
gets an ordinary completion that says why, so its code does not break.

Agents that call their model directly use [`../02-custom-agents/`](../02-custom-agents/). For the
templates and the troubleshooting table, see [`../README.md`](../README.md).

---

## Set up once in Studio

Use a project that only this notebook uses. When the budget is used up, **every** prompt in the
project is blocked.

1. Sign in at [studio.highflame.ai](https://studio.highflame.ai) and create a project, for example
   `cost-controls-ai-gateway`.
2. **AI Gateway → Policies → Cost Controls → Set budget.** Set **Daily budget (USD)** to `0.05` and
   select **Deploy**.
3. In the same tab, deploy the **Daily Budget** template. The deploy dialog starts on **Monitor**;
   set **Enforcement Mode** to **Enforce**.
4. In the same project, create an API key: **AI Gateway → Settings → API Keys**.

```bash
cp .env.example .env      # HIGHFLAME_API_KEY from step 4, and your OpenAI key in PROVIDER_API_KEY
pip install -r requirements.txt
```

---

## Run the proof

```bash
jupyter lab cost_controls_ai_gateway.ipynb
```

The notebook registers an agent, calls `gpt-4o` through the gateway with the ordinary OpenAI client,
and keeps going until the budget is used up. The committed outputs are a run on studio.highflame.ai:

```
project today: [####................]  22% of $0.05 (~$0.011)     <- call 1
 2  allowed   tokens 3101/400   reported by the gateway   [#########...........]  46% of $0.05 (~$0.023)
 3  allowed   tokens 3101/307   reported by the gateway   [#############.......]  67% of $0.05 (~$0.034)
 4  allowed   tokens 3101/400   reported by the gateway   [##################..]  91% of $0.05 (~$0.045)
 5  allowed   tokens 3101/400   reported by the gateway   [####################] 100% of $0.05 (~$0.050)  USED UP
 6  BLOCKED   tokens -          -                         [####################] 100% of $0.05 (~$0.050)  USED UP

What the agent got back:
  Highflame Security: Prompt blocked: this project has used its daily AI budget.

Today, this project: $0.0574 over 5 calls

By agent
  cost-gateway-1238c0          $0.0574    5 calls  100%
```

Call 5 crossed the budget and completed; call 6 was refused before it reached OpenAI. The notebook
ends by deactivating the agent it registered.

`smoke_test.py` reads the budget and spends nothing:

```bash
python smoke_test.py
```
