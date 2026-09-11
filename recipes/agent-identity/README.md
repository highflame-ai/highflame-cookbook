# Agent identity · agents with their own identity, authorization, guardrails and telemetry

**The value:** *"Our agents all run on one shared service key. When something goes wrong we
can't tell which agent did it, we can't give one agent less access than another, and we
can't revoke one without revoking all of them."*

This recipe gives an agent four things from Highflame, then scales the same model to a team of
agents. It ships for two toolkits, [LangGraph](https://langchain-ai.github.io/langgraph/) and
[AWS Strands](https://strandsagents.com), and the LangGraph version comes in two forms: the SDK
middleware inside the agent, or the AI gateway in front of the model. Pick the one you already
use; the four pillars below are identical in all of them.

1. **Agent identity.** Each agent is registered with Highflame and runs on its own key.
   Every decision Highflame makes is recorded against *that agent*.
2. **Agent authorization.** Two layers. The agent's credential policy is a ceiling enforced when
   a credential is issued — a scope outside it is refused before any policy runs. Your policies
   then decide the rest, per tool, and each refusal names the policy that made it. Authority
   handed to another agent is narrowed to what the delegator holds, never widened.
3. **Agent runtime guardrails.** Each user prompt, tool call, tool result and model reply goes
   to Highflame before it proceeds, so prompt injection, data leaks and unsafe replies are
   stopped in flight.
4. **Agent telemetry.** Your OpenTelemetry spans and Highflame's decisions share one trace.
   Each decision carries a request ID, the policies that decided it, the signals that fired
   and, when the request asks for them, every detector that ran.

The **Multi-Agent** half turns the agent into an orchestrator that issues each specialist a
short-lived credential of its own. Authority only narrows on the way down, every decision
is attributed to the specialist that caused it, and revoking the orchestrator revokes the
whole team.

---

## Set it up in Studio

1. **Register an identity in Studio, and copy its key.** [Highflame Studio](https://studio.highflame.ai)
   → **Registry** → **Agents** → **Inventory** → **Register Identity**. The key starts with
   `zid_sk_` and is shown once, on creation, so copy it then.

   An identity's authority ceiling is the **credential policy** attached to it at registration.
   Create the policy first (**Registry** → **Policies** → **Create Policy**), then pick it when
   you register the identity. Which identity, and which scopes on its policy, depends on the
   notebook:

   | Notebook | Register | Scopes on its credential policy |
   | --- | --- | --- |
   | `langgraph_agent_identity` | type `agent`, sub type `orchestrator` | `nhi:manage`, `tools:read`, `tools:execute`, `orders:read`, `kb:read` |
   | the two Strands notebooks | type **Human Proxy** — something acting for a person | `nhi:manage` |

   In the LangGraph notebook this identity **is** the orchestrator: it registers the specialists
   and delegates to them, so its policy's scopes are the ceiling on everything it can hand out.
   Omit `orders:read` or `kb:read` and delegation quietly narrows them away, leaving a specialist
   with less authority than the code asked for and no error to say so. In the Strands notebooks
   the identity only registers agents and never runs one.

   Either way the registrations are attributed to your identity rather than to a shared key, which
   is the same principle the rest of the recipe demonstrates, applied to you.

   **`nhi:manage` is required in both cases, and it is the one people miss.** It is what lets a
   key register other identities. Without it the identity is created, the key works and
   `whoami()` succeeds, and then the first registration fails with
   `403 token missing nhi:manage scope`.
2. **Deploy the guardrail policy templates from Studio.** Highflame ships its guardrails as
   templates and enforces nothing until you deploy them. In Studio → **Guardrails** →
   **Policies**, deploy from the template catalog:

   | Template | Mode | Why |
   | --- | --- | --- |
   | **Structural PII** (`privacy.defaults`) | enforce | The LangGraph notebook's blocked-prompt step leaks a card number and a national ID. PII of that shape is matched by deterministic pattern detectors, which run on every deployment. |
   | **Secrets Detection** (`data-protection.defaults`) | monitor | The LangGraph telemetry step leaks an API key. In monitor mode it is observed and recorded, not blocked, which is what that step demonstrates. |

   The gateway notebook is decided by the **AI Gateway** product's policies instead: deploy the
   same two from Studio → **AI Gateway** → **Policies** (its Secrets Detection template is
   `data-protection.secrets`). Policies belong to a product, so the Guardrails set does not
   apply to gateway traffic and this set does not apply to the middleware path.

   Leave the **Default Behavior** strip at the top of Guardrails → Policies at *Allow by
   default*. Tool results and model replies are permitted by that setting rather than by any
   template, so with it switched to Fail Close the first guarded turn is refused with no policy
   named. For the gateway notebook, open AI Gateway → Policies in Studio once before the first
   run; if the setup cell's first model call is refused as `Security policy violation`, that page
   has not been opened for this project yet.

   Deploy from the UI rather than seeding by script: the deployment is then recorded, attributed
   and reversible like any other policy change. Injection & Jailbreak
   Detection is a model, so a deployment without the detector model servers allows the attempt
   through and a step built on it demonstrates nothing; the Strands notebooks still rely on it,
   and it is on by default for new hosted accounts.
3. **Allow-list what the LangGraph agent may do.** Open the identity in Studio's Registry, go to
   its **Policies** page, switch **Access** to **Enforcing**, and add two grants: **Send prompts →
   Allow all**, and **Call tool →** `lookup_order`, `search_kb`, `ask_orders_specialist`,
   `ask_kb_specialist` (leave the MCP server field empty — these are local tools). Every action is
   locked once enforcement is on, so this ledger is the complete list of what the agent may do;
   `delete_order` is deliberately not on it, and that is what refuses it in the authorization step.
   Send prompts is the grant people forget: without it the first turn is refused. Only this agent
   is switched to Enforcing; the specialists registered from code keep the default Access
   setting, so they are unaffected. Skip this step and the authorization cell reports the other
   state honestly — the tool ran, and it says so.

## Set up a model

**LangGraph notebooks.** Two notebooks, two places for the model call.

| Notebook | What you set | What you get |
| --- | --- | --- |
| `langgraph_agent_identity`, straight to the provider | `OPENAI_API_KEY` (and `OPENAI_BASE_URL` for any OpenAI-compatible server), `MODEL_ID` | The four pillars, from the SDK middleware inside the agent. The model call itself is not governed. |
| `langgraph_gateway_agent_identity`, through the gateway | `HIGHFLAME_GATEWAY_BASE_URL`, `PROVIDER_API_KEY`, `GATEWAY_MODEL_ID` | The four pillars, from the gateway in front of the model, with no Highflame code in the agent. The model call is inspected and recorded too, attributed to the calling agent; whether it can be *refused* depends on the policies attached to the AI Gateway product. |

The gateway needs no key of its own. Two credentials travel in two headers and are not
interchangeable. `X-Highflame-APIKey` says who is calling, and the notebook fills it with the
**acting agent's** key — or `X-Highflame-Token` when the acting agent holds a delegated
credential — so the gateway's record of the model call names the same agent as the guardrail
decisions. `Authorization: Bearer` is forwarded upstream, so it carries `PROVIDER_API_KEY` and
never a Highflame credential.

The gateway is bring-your-own-key for OpenAI-compatible providers: it injects no provider key of
its own, so `PROVIDER_API_KEY` is required. Omit it and the provider answers
`401 You didn't provide an API key`. A model inside your network that takes no key still needs
a value there; any non-empty string will do.

The gateway speaks the OpenAI API, so the same variables point the notebook at a model served
inside your own network, which is what makes the recipe work with no internet access.
`GATEWAY_MODEL_ID` names the model as the gateway does, `provider/model`, and defaults to
`openai/gpt-4o-mini`; a model behind an OpenAI-compatible server is `openai/<its name>`.

**Strands notebooks, on AWS Bedrock.**

- Credentials that can call Amazon Bedrock, through the normal boto3 chain. An SSO profile
  works: `aws sso login --profile <name>` and set `AWS_PROFILE=<name>`.
- Model access for Strands' default Bedrock model in your region, or set `BEDROCK_MODEL_ID`.
- *Optional:* an IAM role with Bedrock invoke permissions that your principal may assume.
  With `AGENT_ROLE_ARN` set, each agent assumes it under its own identity name, so
  CloudTrail attributes model calls to the same agent Highflame does.
- *Optional:* an S3 bucket for `SESSION_BUCKET`, to persist the multi-agent conversation
  under the same id Highflame uses for its decisions.

## Four notebooks

| Notebook | Toolkit | Pattern | What it adds |
| --- | --- | --- | --- |
| [`langgraph_agent_identity.ipynb`](langgraph_agent_identity.ipynb) | LangGraph | One agent, then an orchestrator calling specialists as tools | The four pillars on a single agent; delegated credentials per specialist. Runs against a self-hosted deployment and your own model by setting three variables |
| [`langgraph_gateway_agent_identity.ipynb`](langgraph_gateway_agent_identity.ipynb) | LangGraph + AI gateway | The same two patterns, with every model call routed through the Highflame AI gateway | No Highflame code in the agent. The gateway checks the prompt, each tool call, each tool result and the reply, and the model call itself; each specialist presents its delegated credential to the gateway, so attribution stays exact |
| [`strands_bedrock_agent_identity.ipynb`](strands_bedrock_agent_identity.ipynb) | Strands | The same two patterns, on Amazon Bedrock | Per-agent IAM roles, so CloudTrail attributes the model calls to the same agent Highflame does |
| [`strands_swarm_a2a_agent_identity.ipynb`](strands_swarm_a2a_agent_identity.ipynb) | Strands | A [Swarm](https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/) of specialists that hand off to each other, plus a remote agent served over [A2A](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agent-to-agent/) | Hand-offs authorized as tool calls; the remote agent verifies the caller's Highflame credential at its front door (`401` without one, `403` without the right permission) and runs its own guardrails as itself |

Read the row that matches your toolkit. The two Strands notebooks are in order: the second assumes
the first.

## Run the proof

```bash
cd recipes/agent-identity
cp .env.example .env            # a model credential: OPENAI_API_KEY, or the gateway variables;
                                # AWS_PROFILE for Strands. HIGHFLAME_API_KEY too for the Strands
                                # notebooks -- the LangGraph one prompts for it when unset, so the
                                # key stays out of the notebook's saved output.
pip install -r requirements.txt
jupyter lab                     # open any of the three notebooks
```

Run the cells top to bottom. What you'll see:

| Step | What happens |
| --- | --- |
| Connect as the agent | LangGraph: the Studio-registered agent, nothing registered from code. Strands: an identity and key are created for it. Either way `whoami()` shows the agent acting as itself |
| Ask about an order | The agent answers through its tools; every check is allowed |
| Ask for a scope outside its credential policy (LangGraph) | Refused at issuance with `invalid_scope`, before any policy or detector runs; a granted scope is issued exactly, a mix is narrowed and the token's `scopes` claim says which |
| Ask it to delete an order | Refused by the allow-list before the tool body runs: `Authorization Grants — call_tool`. Without the allow-list the cell says the tool ran, and whether it actually did |
| Leak a card number (LangGraph) / try a prompt injection (Strands) | Refused before the model is called, naming the policy: `Refused by Highflame: Enterprise Policies Triggered: privacy.defaults` |
| Telemetry | One line per span; one decision's request ID, the policies that decided it, the signals that fired, and its attribution |
| Multi-agent | The orchestrator delegates to two specialists; the delegated credential is verified and its claims shown. Optionally, deactivate a specialist in Studio and watch its still-valid credential be refused |
| Clean up | The identities created by this run are deactivated; the Studio-registered agent is left alone |

In the gateway notebook a refusal arrives as the model's reply — a completion whose id starts
with `chatcmpl-blocked-` and whose text names the policy — rather than as a raised
`BlockedError`, so an unmodified OpenAI client keeps working; a refused tool call is the reply
that asked for it, so the tool never runs. Its telemetry step reads the decisions back from
Observatory, one row per check, instead of printing one decision inline.

The A2A server in the second notebook listens on `127.0.0.1:9910`; set `A2A_PORT` in `.env` to change it.

The smoke test covers the Highflame half without AWS:

```bash
python smoke_test.py            # registers, delegates, guards, verifies, cleans up
```

## Notes

- **Sessions.** Each step uses its own `session_id`. Highflame scores risk across the turns
  of a conversation, so an injection attempt should not share a session with the ordinary
  requests that follow it. Through the gateway each request is recorded under a session of its
  own: the LangGraph `thread_id` is not forwarded, so decisions and transcript are joined by
  agent and time rather than by one identifier.
- **`await` in the notebook.** Cells call `await agent.invoke_async(...)` (Strands) or
  `await agent.ainvoke(...)` (LangGraph) because Jupyter already runs an event loop.
- **LangGraph needs the async entrypoint even outside a notebook.** `HighflameMiddleware`
  implements its hooks as coroutines, and `agent.invoke()` raises
  `InvalidUpdateError: Expected dict, got <coroutine object>` rather than guarding. Call
  `ainvoke` from an async service, or `asyncio.run(...)` from a synchronous one.
- **Cost in an agent loop.** A turn that uses one tool calls the model twice, so the prompt is
  evaluated twice. Pass `optimize=True` to the middleware or hooks to run only the detectors your
  active policies reference. The notebooks leave it off so every detector shows up in the
  telemetry section.
- **Delegation scopes.** The orchestrator requests exactly the specialist's own scopes. Two
  rules decide what it gets: a requested scope the specialist may not hold refuses the whole
  exchange with `invalid_scope`, and what survives is narrowed to what the orchestrator itself
  holds — silently. Requesting nothing is refused.
- **Bedrock Guardrails** can run alongside Highflame. They filter model input and output;
  Highflame decides per agent identity and also covers tool calls and results. The notebook
  leaves them off so every block you see comes from one place.
