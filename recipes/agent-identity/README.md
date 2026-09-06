# Agent identity · a Strands agent on Bedrock with its own identity, authorization, guardrails and telemetry

**The value:** *"Our agents all run on one shared service key. When something goes wrong we
can't tell which agent did it, we can't give one agent less access than another, and we
can't revoke one without revoking all of them."*

This recipe gives an [AWS Strands](https://strandsagents.com) agent running on Amazon
Bedrock four things from Highflame, then scales the same model to a team of agents:

1. **Agent identity.** Each agent is registered with Highflame and runs on its own key.
   Every decision Highflame makes is recorded against *that agent*.
2. **Agent authorization.** Your policies decide what each agent may do, from its
   permissions and the tools it was granted. A tool the agent was never given is denied
   before it runs.
3. **Agent runtime guardrails.** Four Strands hooks send each user prompt, tool call, tool
   result and model reply to Highflame before it proceeds, so prompt injection, data leaks
   and unsafe replies are stopped in flight.
4. **Agent telemetry.** Strands' OpenTelemetry spans and Highflame's decisions share one
   trace. Each decision carries a request ID, the detectors that ran, and a signed receipt.

The **Multi-Agent** half turns the agent into an orchestrator that issues each specialist a
short-lived credential of its own. Authority only narrows on the way down, every decision
is attributed to the specialist that caused it, and revoking the orchestrator revokes the
whole team.

---

## Set it up in Studio

1. **Create an API key.** [Highflame Studio](https://studio.highflame.ai) → Settings →
   API Keys → create a key. You want the account key (`zid_sk_...`); the notebook uses it
   only to register agent identities.
2. **Have at least one guardrail policy enabled.** Studio → Policies. Injection & Jailbreak
   Detection is on by default for new accounts; the notebook's blocked-prompt step relies
   on it.
3. *Optional:* a policy that denies tool calls outside an agent's `capabilities`. Without
   one, the authorization step reports "allowed" and tells you so.

## Set up AWS

- Credentials that can call Amazon Bedrock, through the normal boto3 chain. An SSO profile
  works: `aws sso login --profile <name>` and set `AWS_PROFILE=<name>`.
- Model access for Strands' default Bedrock model in your region, or set `BEDROCK_MODEL_ID`.
- *Optional:* an IAM role with Bedrock invoke permissions that your principal may assume.
  With `AGENT_ROLE_ARN` set, each agent assumes it under its own identity name, so
  CloudTrail attributes model calls to the same agent Highflame does.
- *Optional:* an S3 bucket for `SESSION_BUCKET`, to persist the multi-agent conversation
  under the same id Highflame uses for its decisions.

## Run the proof

```bash
cd recipes/agent-identity
cp .env.example .env            # add your HIGHFLAME_API_KEY (and AWS_PROFILE if you use one)
pip install -r requirements.txt
jupyter lab strands_bedrock_agent_identity.ipynb
```

Run the cells top to bottom. What you'll see:

| Step | What happens |
| --- | --- |
| Register the agent | An identity and key are created for the agent; `whoami()` shows the agent acting as itself |
| Ask about an order | The agent answers through its tools; every hook call is allowed |
| Ask it to delete an order | A tool it was never granted; denied if your account enforces capabilities |
| Try a prompt injection | Blocked before Bedrock is called: `Blocked by Highflame: Enterprise Policies Triggered: Injection & Jailbreak Detection` |
| Telemetry | Strands spans on the console; one decision's request ID, detectors and attribution printed |
| Multi-agent | An orchestrator delegates to two specialists; the delegated credential is verified and its claims shown |
| Clean up | The identities created by this run are removed |

The smoke test covers the Highflame half without AWS:

```bash
python smoke_test.py            # registers, delegates, guards, verifies, cleans up
```

## Notes

- **Sessions.** Each step uses its own `session_id`. Highflame scores risk across the turns
  of a conversation, so an injection attempt should not share a session with the ordinary
  requests that follow it.
- **`await` in the notebook.** Cells call `await agent.invoke_async(...)` because Jupyter
  already runs an event loop. Outside a notebook, `agent(...)` works the same way.
- **Delegation scopes.** The orchestrator requests exactly the specialist's own scopes.
  Requesting more is narrowed silently; requesting nothing is refused.
- **Bedrock Guardrails** can run alongside Highflame. They filter model input and output;
  Highflame decides per agent identity and also covers tool calls and results. The notebook
  leaves them off so every block you see comes from one place.
