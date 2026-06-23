# Highflame SDK — Recipes

Interactive, runnable notebooks for the Highflame Python SDK. Each notebook
is a self-contained Marimo app — open it in the browser, run individual cells,
see live output from your own Shield instance.

```
pip install -r requirements.txt
cp .env.example .env          # add HIGHFLAME_API_KEY
marimo run 01_quickstart.py   # or open any notebook below
```

---

## Notebooks

| Notebook | What it covers | Time |
|---|---|---|
| [`01_quickstart.py`](01_quickstart.py) | Connect, evaluate a prompt, the `@shield.prompt` decorator | 5 min |
| [`02_tool_security.py`](02_tool_security.py) | Guard tool calls, `@shield.tool`, rich `ToolContext` | 10 min |
| [`03_agentic_sessions.py`](03_agentic_sessions.py) | Cross-turn session tracking, full OpenAI loop, session delta debug | 15 min |
| [`04_wave_d_decisions.py`](04_wave_d_decisions.py) | All five AARM decisions: allow / deny / modify / step_up / defer | 10 min |

---

## Setup

### Prerequisites

- A [Highflame account](https://studio.highflame.ai) with an API key
- Python 3.10+

### Install

```bash
pip install -r requirements.txt
```

Or with uv:

```bash
uv pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
```

Open `.env` and set:

```
HIGHFLAME_API_KEY=hf_sk_your_key_here
```

For self-hosted Shield, also set `HIGHFLAME_BASE_URL=http://localhost:8080`.

### Run a notebook

```bash
# Interactive Marimo UI in the browser
marimo run 01_quickstart.py

# Or edit + run in the full Marimo editor
marimo edit 01_quickstart.py

# Or run as a plain Python script (non-interactive)
python 01_quickstart.py
```

---

## How the notebooks are structured

Each notebook follows the same shape:

1. **Connect** — create the `Highflame` client from `HIGHFLAME_API_KEY`
2. **Demonstrate** — runnable cells that call Shield and show the response
3. **Explain** — narrative cells that say *why* each field matters
4. **Summarise** — a reference table + link to full docs

Cells are independent: skip any cell that requires setup you don't have
(e.g. the OpenAI loop in `03` skips cleanly without `OPENAI_API_KEY`).

---

## API quick reference

### Client

```python
from highflame import Highflame, Shield, BlockedError

client = Highflame(
    api_key="hf_sk_...",
    base_url="https://api.highflame.ai",  # or self-hosted URL
)
```

### Evaluate a prompt

```python
resp = client.guard.evaluate_prompt("Hello world", session_id="sess_abc")
resp = client.guard.evaluate(
    content="...", content_type="prompt", action="process_prompt"
)
```

### Evaluate a tool call

```python
resp = client.guard.evaluate_tool_call(
    "shell", {"command": "ls -la"}, session_id="sess_abc"
)
```

### Branch on Wave D decisions

```python
if resp.allowed():                         # allow or modify
    content = resp.redacted_content or original
elif resp.is_suspended():                  # step_up or defer
    handle_step_up_or_defer(resp.decision)
else:                                      # deny
    raise BlockedError(resp)
```

### Decorator API

```python
shield = Shield(client)

@shield.prompt                    # guard incoming user message
def chat(message: str) -> str: ...

@shield.tool                      # guard outgoing tool call
def shell(command: str) -> str: ...

@shield.modelresponse             # guard LLM output
def respond(text: str) -> str: ...

@shield.toolresponse              # guard tool return value
def read_file(path: str) -> str: ...
```

All decorators auto-detect `async def` functions.

### Async

```python
resp = await client.guard.aevaluate_prompt("Hello")
async for event in client.guard.astream(request):
    print(event.type, event.data)
```

---

## Enforcement modes

| Mode | Behaviour |
|---|---|
| `enforce` (default) | Block on deny — the wrapped function is never called |
| `monitor` | Allow everything + log; `actual_decision` shows what would have happened |
| `alert` | Allow + fire an alert signal; useful for tracking without blocking |
| `modify` | Detect PII + redact; always returns `decision="modify"` or `"allow"` |

```python
resp = client.guard.evaluate_prompt(content, mode="monitor")
print(resp.decision)        # always "allow" in monitor mode
print(resp.actual_decision) # what would have happened in enforce mode
```

---

## Studio setup for each notebook

| Notebook | Policies to enable |
|---|---|
| 01 Quickstart | Secrets Detection → enforce |
| 02 Tool Security | Tool Governance → call_tool scope |
| 03 Sessions | Any policy with cross-turn accumulation |
| 04 Wave D | PII Redaction → modify mode; Step-up policy (optional) |

Enable policies in **Studio → Guardrails → Policies**.

---

## Need help?

- [SDK reference](https://docs.highflame.ai/sdk)
- [Policy authoring guide](https://docs.highflame.ai/policies)
- [Studio](https://studio.highflame.ai)
