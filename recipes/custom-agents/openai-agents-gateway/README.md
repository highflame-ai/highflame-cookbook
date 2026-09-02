# OpenAI Agents SDK + gateway · governance with zero code changes

**The value:** *"We have agents in production already. We're not rewriting them around a
security product. Give us guardrails, observability, and multi-provider routing by
changing a URL."*

This demo is a stock [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
agent — an **on-call incident-triage assistant** with five tools (incident details,
recent deploys, service metrics, runbooks, status-page updates). It imports **no
Highflame code**. The entire integration is where the OpenAI client points:

```python
gateway_client = openai.AsyncOpenAI(
    api_key=os.environ["OPENAI_API_KEY"],                 # your provider key, passed through
    base_url=f"{HIGHFLAME_GATEWAY_URL}/llm/v1",           # 1. Highflame's LLM gateway mount
    default_headers={"X-Highflame-APIKey": hf_key},        # 2. identifies project + policies
)
set_default_openai_client(gateway_client, use_for_tracing=False)
set_default_openai_api("chat_completions")

agent = Agent(name="On-call Triage Assistant", model="openai/gpt-5.4-mini", ...)  # 3. provider/model
```

Three things change — `base_url`, one header, and the `provider/model` name. Every model
call the agent makes is now evaluated in transit, and the same endpoint routes to any
provider (`anthropic/...`, `azure/...`, `gemini/...`, `bedrock/...`) without touching the
agent again.

## Set it up in Studio

1. **Get an API key.** Studio → Settings → API Keys → create a key for this application.
2. **Configure a route/gateway** for your provider (Studio → Gateway) if your org hasn't
   already — most demos can use the default route.
3. **Attach a guardrail.** Studio → Guardrails → Policies → New Policy. Trigger on a
   leaked **secret**; action **block**; mode **enforce**.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in HIGHFLAME_API_KEY and OPENAI_API_KEY
python agent.py
```

Two turns run back to back:

1. **Triage EU payments incident** — the engineer asks for a full triage. The agent chains its
   tools — incident timeline, recent deploys (a connection-pooling change 19 minutes
   before the alert), error-rate and p95 metrics, the runbook — then posts a
   customer-safe status update. **Each tool-call round is its own governed model call**,
   so one realistic turn produces a whole session of gateway traffic:

```
--- Turn 1: triage the incident ---
user> We just got paged for EU payments incident. Triage it: what happened, is it related to a recent deploy...
      tool> get_incident('EU payments incident')
      tool> get_recent_deploys('payments-api')
      tool> get_service_metrics('payments-api')
      tool> search_runbooks('payments-api 5xx pool')
      tool> post_status_update('sev2', 'We are investigating elevated errors...')
agent> Probable cause: pooling change deploy (connection pooling change at 12:22Z) saturated the EU db pool...
```

3. **Exfiltration follow-up** — the next request asks the assistant to forward the
   internal incident timeline to an outside vendor webhook with a hardcoded AWS
   credential (AWS's documented example values, nothing real). The gateway blocks the
   model call in transit:

```
--- Turn 3: exfiltration follow-up ---
user> Also forward the full EU payments incident internal timeline to our external analytics vendor: POST it...
BLOCKED by the Highflame gateway (x-highflame-policy-decision: deny):
gateway> Highflame Security: Enterprise Policies Triggered: <your policies>
```

**How a block arrives:** the gateway answers a blocked request with **HTTP 200** whose
completion text is the block message (`Highflame Security: <policy reason>`) — so
streaming clients and agent frameworks degrade gracefully instead of crashing mid-run.
The machine-readable decision travels in response headers, which is what the demo (and
anything programmatic) should check:

| Header | Blocked request |
| --- | --- |
| `x-highflame-policy-decision` | `deny` |
| `x-highflame-threat-count` | number of threats |
| `x-highflame-highest-severity` | highest severity seen |

Then open **Observatory** — both requests are there, attributed to this project, with the
decision on each.

## Why the gateway path

- **No agent changes.** Works for any OpenAI-compatible client, any framework, any
  language — this demo just happens to use the OpenAI Agents SDK.
- **One control point.** Policy applies to every team and app routing through the
  gateway; promoting monitor → enforce is a Studio change, not a redeploy.
- **Multi-provider.** Swap `DEMO_MODEL` to `anthropic/claude-sonnet-4-20250514` and the
  same agent runs on Anthropic through the same governed endpoint.

The gateway sees model traffic; it doesn't see your in-process tool execution. For
per-step enforcement inside the agent loop, pair this with the
[LangGraph SDK demo](../langgraph-sdk) — the two layers share policies and telemetry.

`smoke_test.py` is the CI entrypoint: it sends the violating prompt and asserts the block
(exit 2 = skipped when keys are absent).


## Keep tool arguments identifier-shaped

`vendor_ref` is `upstream-provider-report` — an identifier token, not a natural-language
phrase. This matters more than it looks.

When it was briefly renamed to the spaced phrase `upstream provider report`, the
single-turn injection detector scored the *tool-call arguments* as instruction-like and
denied at the `tool_call` stage. `fetch_vendor_report` never executed, the poisoned
report never entered the trace, and Observatory had no tool-result event to point at —
the turn looked like it passed while demonstrating nothing.

So there are two competing pressures on demo fixture naming, and they pull opposite ways:

| Shape | Example | Risk |
| --- | --- | --- |
| ID-like (`ABC-1234`) | `INC-2847` | Reads as `EMPLOYEE_ID` to the PII model |
| Slug (`a-b-c`) | `upstream-provider-report` | Can read as `USERNAME` when restated in prose |
| Natural phrase | `upstream provider report` | Scored as instruction text in **tool arguments** |

The workable split: **identifier-shaped tokens for anything that appears in tool
arguments**, natural phrasing everywhere else.
