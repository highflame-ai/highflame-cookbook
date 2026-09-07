# AI gateway · point anything that speaks the OpenAI API at Highflame

**The value:** *"We have tools and agents calling model providers directly. We cannot see what
they send, we cannot stop what we would not allow, and we cannot tell who called."*

Change one base URL and add one header, and every request is inspected, recorded and attributed to
the caller before it reaches your provider. No SDK, and no code change beyond those two lines.

## Start here

| If you want to | Read |
| --- | --- |
| Understand what the gateway does to your traffic, runnably | [`gateway_quickstart.ipynb`](gateway_quickstart.ipynb) |
| Point Claude Code at the gateway | [`claude.md`](claude.md) |
| Point Codex at the gateway | [`codex.md`](codex.md) |
| Point GitHub Copilot at the gateway | [`copilot.md`](copilot.md) |

The notebook is the one to read first if you are evaluating. The three guides are configuration
recipes for a tool you already use.

## Run the notebook

```bash
cd recipes/ai-gateway
cp .env.example .env            # add HIGHFLAME_API_KEY and PROVIDER_API_KEY
pip install -r requirements.txt
jupyter lab                     # open gateway_quickstart.ipynb
```

## Two things that surprise people

**The gateway is bring-your-own-key for OpenAI-compatible providers.** It forwards the
`Authorization` header upstream and injects no provider key of its own, so on a default account
`PROVIDER_API_KEY` is required.

Your Highflame key is accepted in either `X-Highflame-APIKey` or `Authorization: Bearer`. The three
tool guides above use the bearer, because Codex and Copilot can only send one credential. Prefer
the dedicated header whenever you can, because it leaves `Authorization` free for your provider
key. Put the Highflame key in the bearer and nothing carries the provider key, which is the
`401 You didn't provide an API key` a few readers hit.

**Refusal is not switched on by default.** The gateway inspects and records every request, but
whether it refuses one depends on which policies are attached to the `ai_gateway` product and in
which mode. A policy attached to a different product is not consulted here, and a policy in
`monitor` records what it would have done and lets the request through. Attach what you want under
Studio → AI Gateway → Policies and set each to `enforce`.

**And it fails open.** If the inspection service is unreachable, traffic is forwarded with a
warning rather than refused, so an outage costs you scanning rather than availability. Set
`shield.fail_closed = true` if an unavailable guardrail must block instead.

## Related

[`recipes/agent-identity/`](../agent-identity/) gives each agent its own credential, so the caller
the gateway records is the agent rather than your account key.
