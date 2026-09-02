# LangGraph + SDK · inline guardrails in an autonomous workflow

**The value:** *"Our LangGraph workflows run with nobody watching — triggered by webhooks
and queues, not by a person typing into a chat box. The threat isn't a malicious user;
it's poisoned data flowing through the workflow. We want enforcement at every step, in
code, so an injected instruction never reaches the model and a bad tool call never
executes."*

This demo is an autonomous **ticket-enrichment worker**: it drains a queue of inbound
support tickets delivered by a webhook and runs a LangGraph agent over each one — the
shape most production LangGraph deployments actually take. The entire Highflame
integration is one middleware line:

```python
from highflame.integrations.langgraph import HighflameMiddleware

middleware = HighflameMiddleware(client, mode="enforce")
agent = create_agent(model=model, tools=tools, system_prompt=..., middleware=[middleware])
```

That single line guards **every ticket's content before the model sees it**, **every tool
call before it executes** (with the full arguments as context), **every tool result**, and
**every triage output** — for every run of the worker, on every ticket.

## Set it up in Studio

1. **Get an API key.** Studio → Settings → API Keys → create a key for this agent.
2. **Attach a guardrail.** Studio → Guardrails → Policies → New Policy. Trigger on a
   leaked **secret**; action **block**; mode **enforce**. (Start in monitor if you want to
   watch decisions in Observatory before enforcing.)

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in HIGHFLAME_API_KEY and OPENAI_API_KEY
python agent.py
```

The worker drains a five-ticket queue. Three are routine — an SSO lockout, a
double-billing dispute (multi-tool: account lookup + billing history + KB), an API
latency report that fetches a clean attachment. **Two are poisoned, and they're caught
at two different points in the agent loop:**

| Ticket | Where the payload lives | Guard hook | Detector exercised |
| --- | --- | --- | --- |
| **export request ticket** | A customer pastes their live AWS keys into the body while asking for help with a failing export. **No instruction to the agent anywhere in it** | Prompt guard (`before_model`) — model never called | **Secrets** |
| **sync failure ticket** | The ticket reads **completely clean**. It references a customer-supplied attachment; the payload only enters when the agent **fetches that document and the poisoned text returns in a tool result** | Tool-result guard (`wrap_tool_call`) — mid-loop | **Injection** |

The two are kept strictly disjoint **in both directions**: the injection ticket carries
no credential, and the credential ticket carries no instruction to the agent. Mix them
and the louder detector fires first, masking the other — so neither case demonstrates
the detector it is named for. (Credentials are AWS's documented example values, so
nothing real.)

Credential disclosure is also the more realistic of the two: customers paste live keys
into support tickets constantly, with no malice at all.

sync failure ticket is the one worth dwelling on: it's textbook **indirect prompt injection**.
Nothing the operator wrote is malicious, no human ever reviewed the fetched document,
and the agent asked for it in the normal course of doing its job. The worker
quarantines each and keeps draining the queue:

```
[worker] billing dispute ticket received (portal, Nordwind account): 'Charged twice in July'
      tool> lookup_account('Nordwind account')
      tool> get_billing_history('Nordwind account')
      tool> search_kb('duplicate invoice')
[worker] billing dispute ticket enriched:
      route: billing
      priority: P2
      ...

[worker] export request ticket received (email, Helix account): 'Re: data sync question'
[worker] export request ticket QUARANTINED — Highflame blocked it: <your policy's reason>

[worker] sync failure ticket received (email, Helix account): 'Initial sync still failing'
      tool> lookup_account('Helix account')
      tool> fetch_linked_document('sync notes attachment')
[worker] sync failure ticket QUARANTINED — Highflame blocked it: <your policy's reason>

[worker] cycle complete: 3 enriched, 2 quarantined
```

Note the difference in the trace: export request ticket is blocked with **no tool calls at all**
(the prompt never reached the model), while sync failure ticket shows the agent doing legitimate
work right up until the fetch returns poisoned content.

Then open **Observatory**: each ticket is one session (`thread_id` = ticket ID). Open
`sync failure ticket` to show the block landing mid-loop on a tool result, with no human anywhere
in the loop.

## Why the SDK path

- **Autonomous workflows are exactly where inline guards earn their keep** — nobody
  reviews these runs, and the injection arrives inside the data, not from a user.
- Enforcement lives next to the code path where actions happen — the model call, the tool
  call, the response — not just at the network edge.
- Tool calls are guarded with their **arguments** as context, so policy can reason about
  *what the tool was asked to do*, not just that a tool ran.
- The model call itself stays in your app with your provider key. Pair this with the
  [gateway demo](../openai-agents-gateway) to also govern model traffic centrally — the
  two layers share policies and telemetry.

`smoke_test.py` is the CI entrypoint: it runs the poisoned ticket and asserts the
quarantine (exit 2 = skipped when keys are absent).
