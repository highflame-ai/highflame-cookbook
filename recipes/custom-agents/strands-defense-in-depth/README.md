# AWS Strands + SDK · agent-loop guardrails and loop detection

**The value:** *"The gateway governs everything that crosses it — but our agents also
act outside a model request: scheduled jobs, retry paths, runbook automation. We want
those governed by the same policies, with the same evidence."*

This demo is an AWS Strands fleet-operations agent secured by **both integration
paths at once** — the pattern most production deployments actually run:

| Layer | How it's wired | What it catches |
| --- | --- | --- |
| **Gateway** | The Strands OpenAI provider takes a pre-configured client, so `client_args` point model traffic at Highflame | Every model call, governed in transit — no agent code involved |
| **SDK** | `HighflameStrandsHooks(...)` on the agent loop | Session-scoped behaviour across a whole run — loop detection, cumulative risk, session sensitivity |

```python
gateway_client = openai.AsyncOpenAI(                       # LAYER 1
    api_key=os.environ["OPENAI_API_KEY"],
    base_url=f"{GATEWAY_URL}/llm/v1",
    default_headers={"X-Highflame-APIKey": hf_key},
)
model = OpenAIModel(client=gateway_client, model_id="openai/gpt-5.4-mini")

hooks = HighflameStrandsHooks(client, mode="enforce")      # LAYER 2

agent = Agent(model=model, tools=[...], hooks=[hooks])
```

## Why both

**The gateway blocks tools before they execute.** firehog evaluates every tool call in
the model's response and, on deny, replaces that response outright
(`src/gateway/llm/mod.rs:2441`) — the agent never receives the `tool_use` directive. It
can also **redact tool-call arguments in flight**. If you have heard "you need the SDK
for pre-execution tool blocking", that is wrong.

What the SDK adds is **session-scoped behavioural state inside the agent loop** —
cross-turn signals like loop detection, cumulative risk, and session sensitivity that
come from watching a whole run rather than individual requests. Turn 3 is that case.

An earlier version of this demo guarded a hardcoded function call with no model
anywhere in it, to argue the gateway had a blind spot. That argument was wrong and has
been removed: a Python function calling another with literal arguments is ordinary
authorization, not agent security. **Everything in this demo is AI-driven.**

## Set it up in Studio

1. **API key** — Studio → Settings → API Keys.
2. **A tool-governance policy** (block + enforce) on destructive fleet operations —
   covers turn 2. Without it, turn 2 is allowed and the demo proves nothing.
3. *(Optional)* a policy referencing `loop_detected`, if you want turn 3 to block
   rather than just flag.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in the two keys; set the dev URLs if testing dev
python agent.py
```

Three turns, each landing at a **different layer**:

| Step | Expected | Stopped by | Why that layer |
| --- | --- | --- | --- |
| 1 · routine fleet question | allowed; agent chains `fleet_status` + `recent_changes` | — | — |
| 2 · destructive wipe, **model-requested** | **`block-gateway`** — denied pre-execution; the agent never gets the directive | Gateway, in transit | The tool call rides in the model's response, so the proxy sees it |
| 3 · **runaway retry loop** — the model keeps polling a node that never recovers | `loop_detected` flagged (blocks only if a policy references it) | SDK, session state | Not an attack: an agent burning quota and never converging |

Turn 2 carries no credential, on purpose: it has to be stopped by tool-governance
policy reasoning about the *arguments*. Mixing a credential in would trip secrets
detection first and prove nothing about tool governance.

Turn 3's loop is driven by the model, not a scripted `for` loop — the agent is told to
poll until recovery and the tool never reports recovery, so the model itself decides to
call it repeatedly. How many polls it makes before giving up varies by model; if it
stops short of the threshold, lower `loop_detector`'s threshold via a detection rule
(minimum 2) rather than faking the loop in code.

The run ends with a layer summary so the split is explicit:

```
Layer summary:
  routine (read-only)           -> allow
  destructive via the model     -> block-gateway   (gateway stops it pre-execution)
  runaway retry loop            -> loop detection, not an attack
```

## Environment

Defaults target the SaaS. For dev set **all three** URLs in `.env` — including
`HIGHFLAME_TOKEN_URL`. A dev service key will not exchange against the SaaS auth
host; you get `[400] Bad Request: invalid api key` from the token exchange before any
guard call is made.

`HIGHFLAME_OPTIMIZE=true` runs only the detectors your active policies reference.
Worth setting if, for example, your PII policy is structural-only and you don't want
the ML PII model executing on every guard call — an agent loop re-guards the same
prompt once per tool round, so the saving compounds.

`smoke_test.py` is the CI entrypoint: it runs **turn 2** and asserts the block
(exit 2 = skipped when keys are absent).


## On loop detection and budgets

**Loop detection works.** Shield's `loop_detector` counts consecutive calls to the same
tool within a session and flags at a threshold — **default 10**, configurable down to 2
via a detection rule. Turn 3 lets the model poll until it gives up, so how far it gets varies by run. Whether it *blocks* depends on a policy referencing `loop_detected`;
without one you will still see `is_loop_detected` on the events in Observatory.

This is worth showing precisely because it is **not an attack**. Nothing in the content
is malicious. It is an agent stuck in a retry loop — an availability and cost failure —
caught by the same control plane as the injection and the credential.

**Budget enforcement currently cannot fire.** The `budget_checker` detector exists and
emits `budget_remaining_pct` / `budget_exceeded`, and session state accumulates
`TokenBudget.Used` from `ModelContext.tokens_used`. But **`TokenBudget.Limit` is never
assigned anywhere in Shield's non-test code**, so `computeBudget` short-circuits on
`Limit <= 0` and always returns 100% remaining, not exceeded.

No budget scenario is included here on purpose: it would appear to pass while proving
nothing. Once a limit can be set — via policy, detection rule, or the guard request —
the natural demo is a fan-out task that exhausts the session's token budget mid-run.
