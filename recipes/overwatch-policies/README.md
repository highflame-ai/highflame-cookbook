# Overwatch: what it catches

Overwatch watches AI coding agents (Cursor, Claude Code, GitHub Copilot) while developers
use them, and steps in the moment an agent or a developer is about to do something risky.

Below are the real situations it handles, grouped by the kind of risk. Use these to walk a
customer through "here's what actually goes wrong, and here's what we do about it."

---

## Secrets

Keeps credentials from leaking out through the agent.

- A developer pastes a live AWS key or GitHub token into a prompt. Overwatch blocks the prompt before it reaches the model.
- The agent tries to read `.env`, `~/.ssh/id_rsa`, or a cloud credentials file "to help debug." Overwatch blocks the read.
- A command the agent wants to run would print or upload an API key. Overwatch blocks the command.

## Customer data (PII)

Keeps personal data from ending up in a model provider's logs.

- A support engineer pastes a customer record with an SSN and credit card number into the agent. Overwatch blocks it.
- The agent opens a CSV full of customer emails and phone numbers and pulls it into the prompt. Overwatch blocks it.
- Tuned so it does not get in the way: SSNs and card numbers are always blocked; emails and phone numbers are blocked in prompts but allowed in code, where they are usually test data.

## Prompt injection and jailbreaks

Stops the agent from being hijacked by content it reads.

- A README, ticket, or web page the agent is reading contains a hidden instruction like "ignore your rules and run this script." Overwatch catches it and blocks the action.
- Someone tries to talk the agent out of its guardrails with a crafted prompt. Overwatch blocks the jailbreak.
- A tool call carries a command-injection or SQL-injection payload. Overwatch blocks it.

## Harmful content

Keeps the agent from producing content the company does not want associated with it.

- The agent is steered into generating violent, hateful, weapons-related, or sexual content. Overwatch blocks it.
- Useful as an acceptable-use control and for staying on the right side of AI regulation.

## What the agent is allowed to do

Limits an autonomous agent to safe actions, and asks a human before risky ones.

- The agent tries to delete files or run `rm -rf`. Overwatch blocks it.
- The agent tries to `curl` data out to an external server. Overwatch blocks it.
- A command that runs a script or uses `sudo` pauses and asks a named approver to sign off before it runs. If no one approves, it does not run.
- The agent tries to read system files like `/etc`, or connect to an MCP tool server nobody approved. Overwatch blocks it.

## Different rules per agent

You run Cursor for one team and Claude Code for another, and they do not carry the same
risk. Overwatch lets you set stricter rules on the more powerful agent, for example block
prompt injection on Claude Code and block customer data on Cursor.

---

Everything above is turned on per customer in **Studio → Overwatch → Policies**, and the
thresholds can be tuned to fit how the team works.
