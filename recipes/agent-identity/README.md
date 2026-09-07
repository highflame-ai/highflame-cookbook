# Agent identity · agents with their own identity, authorization, guardrails and telemetry

**The value:** *"Our agents all run on one shared service key. When something goes wrong we
can't tell which agent did it, we can't give one agent less access than another, and we
can't revoke one without revoking all of them."*

This recipe gives an agent four things from Highflame, then scales the same model to a team of
agents. It ships for two toolkits, [LangGraph](https://langchain-ai.github.io/langgraph/) and
[AWS Strands](https://strandsagents.com). Pick the one you already use; the four pillars below are
identical in both.

1. **Agent identity.** Each agent is registered with Highflame and runs on its own key.
   Every decision Highflame makes is recorded against *that agent*.
2. **Agent authorization.** Two layers. The agent's credential carries the permissions it
   holds, checked before any policy runs, so an action it does not authorize is refused
   outright. Your policies then decide the rest, including whether a specific tool is on the
   agent's declared list.
3. **Agent runtime guardrails.** Each user prompt, tool call, tool result and model reply goes
   to Highflame before it proceeds, so prompt injection, data leaks and unsafe replies are
   stopped in flight.
4. **Agent telemetry.** Your OpenTelemetry spans and Highflame's decisions share one trace.
   Each decision carries a request ID, a signed receipt, and, when the request asks for them,
   every detector that ran.

The **Multi-Agent** half turns the agent into an orchestrator that issues each specialist a
short-lived credential of its own. Authority only narrows on the way down, every decision
is attributed to the specialist that caused it, and revoking the orchestrator revokes the
whole team.

---

## Set it up in Studio

1. **Create an API key.** [Highflame Studio](https://studio.highflame.ai) → **AI Gateway** →
   **Settings** → **API Keys** → **Create API Key**. The value starts with `zid_sk_`, and it is
   shown once, so copy it then. The notebook uses it only to register agent identities.

   Studio has no account-wide API-keys screen. Every key is created from a product's own API
   Keys page, and they are all the same kind of key, so the one above works for this recipe
   whichever page you made it on. `Settings` in the left sidebar does not create keys; its
   `Account & API` section is read-only.
2. **Have at least one guardrail policy enabled.** Policies live under each product, not in a
   top-level Policies screen. For these notebooks: Studio → **Custom Agents** → **Configure** →
   **Policies**. Injection & Jailbreak Detection is on by default for new accounts, and the
   notebook's blocked-prompt step relies on it.
3. *Optional, and only for the second half of the authorization step:* a policy that refuses a
   tool outside an agent's `capabilities`. Without one, that cell reports "allowed" and says so.
   The first half of the authorization step needs nothing configured: it is refused on the
   agent's credential. The notebook gives the exact Cedar rule for the second half.

## Set up a model

**LangGraph notebook.** Three options, in increasing order of what they prove.

| Option | What you set | What you get |
| --- | --- | --- |
| Straight to the provider | `OPENAI_API_KEY` | The four pillars. The model call itself is not governed. |
| Through the gateway | `HIGHFLAME_GATEWAY_BASE_URL` plus `PROVIDER_API_KEY` | The model call becomes a governed, recorded event, attributed to the calling agent. |

The gateway needs no key of its own. Two credentials travel in two headers and are not
interchangeable. `X-Highflame-APIKey` says who is calling, and the notebook fills it with the
**acting agent's** key, so the gateway's record of the model call names the same agent as the
guardrail decisions. `Authorization: Bearer` is forwarded upstream, so it carries
`PROVIDER_API_KEY` and never a Highflame credential.

The gateway is bring-your-own-key for OpenAI-compatible providers: it injects no provider key of
its own, so `PROVIDER_API_KEY` is required. Omit it and the provider answers
`401 You didn't provide an API key`.

The gateway speaks the OpenAI API, so the same variables point the notebook at a model served
inside your own network, which is what makes the recipe work with no internet access.
`MODEL_ID` picks the model and defaults to `gpt-4o-mini`; through the gateway it must name a
model the gateway serves, such as `openai/gpt-4o-mini`.

**Strands notebooks, on AWS Bedrock.**

- Credentials that can call Amazon Bedrock, through the normal boto3 chain. An SSO profile
  works: `aws sso login --profile <name>` and set `AWS_PROFILE=<name>`.
- Model access for Strands' default Bedrock model in your region, or set `BEDROCK_MODEL_ID`.
- *Optional:* an IAM role with Bedrock invoke permissions that your principal may assume.
  With `AGENT_ROLE_ARN` set, each agent assumes it under its own identity name, so
  CloudTrail attributes model calls to the same agent Highflame does.
- *Optional:* an S3 bucket for `SESSION_BUCKET`, to persist the multi-agent conversation
  under the same id Highflame uses for its decisions.

## Three notebooks

| Notebook | Toolkit | Pattern | What it adds |
| --- | --- | --- | --- |
| [`langgraph_agent_identity.ipynb`](langgraph_agent_identity.ipynb) | LangGraph | One agent, then an orchestrator calling specialists as tools | The four pillars on a single agent; delegated credentials per specialist. Runs against a self-hosted deployment and your own model by setting three variables |
| [`strands_bedrock_agent_identity.ipynb`](strands_bedrock_agent_identity.ipynb) | Strands | The same two patterns, on Amazon Bedrock | Per-agent IAM roles, so CloudTrail attributes the model calls to the same agent Highflame does |
| [`strands_swarm_a2a_agent_identity.ipynb`](strands_swarm_a2a_agent_identity.ipynb) | Strands | A [Swarm](https://strandsagents.com/docs/user-guide/concepts/multi-agent/swarm/) of specialists that hand off to each other, plus a remote agent served over [A2A](https://strandsagents.com/docs/user-guide/concepts/multi-agent/agent-to-agent/) | Hand-offs authorized as tool calls; the remote agent verifies the caller's Highflame credential at its front door (`401` without one, `403` without the right permission) and runs its own guardrails as itself |

Read the row that matches your toolkit. The two Strands notebooks are in order: the second assumes
the first.

## Run the proof

```bash
cd recipes/agent-identity
cp .env.example .env            # add HIGHFLAME_API_KEY, plus a model credential
                                # (OPENAI_API_KEY, or the gateway variables; AWS_PROFILE for Strands)
pip install -r requirements.txt
jupyter lab                     # open any of the three notebooks
```

Run the cells top to bottom. What you'll see:

| Step | What happens |
| --- | --- |
| Register the agent | An identity and key are created for the agent; `whoami()` shows the agent acting as itself |
| Ask about an order | The agent answers through its tools; every check is allowed |
| Run an under-permissioned agent | Its prompt is allowed, its tool call is refused on the credential, before any policy or detector. Needs nothing configured |
| Ask it to delete an order | A tool it was never granted; refused only if your account enforces capabilities, and the cell says which happened |
| Try a prompt injection | Blocked before the model is called: `Blocked by Highflame: Enterprise Policies Triggered: Injection & Jailbreak Detection` |
| Telemetry | Spans on the console; one decision's request ID, detectors and attribution printed |
| Multi-agent | An orchestrator delegates to two specialists; the delegated credential is verified and its claims shown |
| Clean up | The identities created by this run are removed |

The A2A server in the second notebook listens on `127.0.0.1:9910`; set `A2A_PORT` in `.env` to change it.

The smoke test covers the Highflame half without AWS:

```bash
python smoke_test.py            # registers, delegates, guards, verifies, cleans up
```

## Notes

- **Sessions.** Each step uses its own `session_id`. Highflame scores risk across the turns
  of a conversation, so an injection attempt should not share a session with the ordinary
  requests that follow it.
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
- **Delegation scopes.** The orchestrator requests exactly the specialist's own scopes.
  Requesting more is narrowed silently; requesting nothing is refused.
- **Bedrock Guardrails** can run alongside Highflame. They filter model input and output;
  Highflame decides per agent identity and also covers tool calls and results. The notebook
  leaves them off so every block you see comes from one place.
