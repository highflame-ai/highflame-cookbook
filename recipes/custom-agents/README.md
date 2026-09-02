# Custom agents · securing the agents you build

**The value:** *"We build our own agents — on LangGraph, on the OpenAI Agents SDK, on AWS
Strands. We want guardrails on every prompt, tool call, and response, with the evidence in
one place — without rebuilding each agent around a security product."*

Highflame secures custom agents two ways: **the SDK**, guarding steps inline in the agent
loop, and **the gateway**, governing model traffic in transit with no agent code changes.
Four demos, each a different framework, integration path, and threat class:

| Demo | Framework · shape | Integration | What it shows |
| --- | --- | --- | --- |
| [`langgraph-sdk/`](./langgraph-sdk) | LangGraph · **autonomous workflow** (webhook-driven ticket-enrichment worker, no human in the loop) | **SDK** | Two poisoned tickets caught at two different hooks by two different detectors: a pasted credential at the prompt guard, an indirect injection in a fetched attachment at the tool-result guard |
| [`openai-agents-gateway/`](./openai-agents-gateway) | OpenAI Agents SDK · **user-facing assistant** (on-call incident triage, six tools) | **Gateway** | A realistic triage turn produces a whole session of governed model calls; an indirect injection and a credential exfiltration are blocked in transit |
| [`strands-gateway-ip/`](./strands-gateway-ip) | AWS Strands · **research-lab assistant** (LIMS, assay store, ELN, SOPs, literature, collaboration portal) | **Gateway** | Keyword-based IP protection: the same protected identifiers pass on internal analysis and are blocked on egress — over-blocking is made as visible as under-blocking |
| [`strands-defense-in-depth/`](./strands-defense-in-depth) | AWS Strands · **fleet-ops agent** | **SDK** | Tool-call argument governance, plus a model-driven retry loop as an agent *reliability* failure rather than an adversarial one |
| [`langgraph-mcp-soc-triage/`](./langgraph-mcp-soc-triage) | LangGraph · **multi-agent SOC team** (four agents, three fronted MCP servers + one deliberate shadow server) | **SDK** | The governance half: per-agent identity with two delegation paths (RFC 8693 `act` chain + `created_by` attenuation), layered authorization (scope refusal at issuance, Cedar 403 at runtime), and a **CIBA step-up approval** gating the one destructive action — all three AARM disposition classes in one run |

> **On "the gateway can't block before a tool runs" — that's false.** firehog evaluates
> every tool call in the model's response and denies the response outright, so the agent
> never receives the directive. It can also redact tool-call arguments in flight. The
> genuine gateway blind spot is narrower: actions your code takes with **no model round
> trip** never cross it — and those are usually ordinary authorization, not agent security.

**Each demo uses one integration path, deliberately.** Running both against the same agent
evaluates every prompt and response twice — double latency, double guard spend, duplicate
events with ambiguous attribution. Either layer is sufficient on its own; pick the one that
fits how the agent is deployed.

## Environment

All four default to the **SaaS** and switch to dev purely through `.env`. For the SDK
recipes set `HIGHFLAME_TOKEN_URL` as well as `HIGHFLAME_BASE_URL` — a dev service key
will not exchange against the SaaS auth host, and the failure (`[400] invalid api key`)
happens at token exchange before any guard call, which reads like a bad key rather than
a wrong environment.

| | SaaS (default) | dev |
| --- | --- | --- |
| Gateway | `https://gateway.highflame.ai` | `https://gateway-dev.highflame.dev` |
| Shield API | `https://api.highflame.ai` | `https://api-dev.highflame.dev` |
| Token exchange | `https://auth.highflame.ai/oauth2/token` | `https://auth-dev.highflame.dev/oauth2/token` |

Both paths enforce the same policies and land in the same Observatory telemetry, so a
decision made inline or at the gateway shows up identically.

## Demo script (suggested order)

1. **`openai-agents-gateway`** first — the "no code changes" story. Show the only three
   things that differ from a stock agent: `base_url`, the `provider/model` name, and the
   `X-Highflame-APIKey` header.
2. **`langgraph-sdk`** second — the "defense inside an unattended workflow" story. One
   middleware line, then an injection arriving inside fetched data and being quarantined
   mid-batch with no human in the loop.
3. **`strands-gateway-ip`** for a customer with IP to protect — the same identifiers
   passing internally and blocked on egress.
4. **`langgraph-mcp-soc-triage`** for a customer asking "what happens when the agent
   *acts*?" — per-agent identity, a runtime 403 with its determining policy, and a
   live CIBA approval in Studio in front of a firewall change. Needs the Studio
   approval pane on screen; budget the extra setup (roles + policies).
5. Open Observatory and show the sessions side by side: same policies, same evidence
   trail, very different integration efforts.

Each subdirectory has its own README with the Studio click-path and the runnable proof.
