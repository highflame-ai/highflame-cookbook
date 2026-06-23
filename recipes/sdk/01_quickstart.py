import marimo

__generated_with = "0.9.0"
app = marimo.App(width="medium", app_title="Highflame SDK — Quickstart")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Highflame SDK — Quickstart

        Three lines of Python to add real-time guardrails to any LLM call.

        ```
        pip install highflame python-dotenv
        cp .env.example .env   # add your HIGHFLAME_API_KEY
        marimo run 01_quickstart.py
        ```

        ---

        ### What you'll see

        1. A benign prompt — Shield **allows** it.
        2. A prompt trying to exfiltrate secrets — Shield **denies** it and
           tells you which policy fired.
        3. The same two prompts via the `@shield.prompt` **decorator** — zero
           boilerplate for wrapping your existing `chat()` function.
        """
    )
    return


@app.cell
def _(mo):
    mo.md("## 1. Connect")
    return


@app.cell
def _():
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from highflame import Highflame, Shield, BlockedError

    client = Highflame(
        api_key=os.environ["HIGHFLAME_API_KEY"],
        base_url=os.environ.get("HIGHFLAME_BASE_URL") or "https://api.highflame.ai",
        token_url=os.environ.get("HIGHFLAME_TOKEN_URL") or "https://auth.highflame.ai/oauth2/token",
    )
    print("Connected ✓  Shield:", client._base_url)
    return BlockedError, Shield, client, os


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. Evaluate a benign prompt

        `evaluate_prompt` is the one-liner shorthand for:
        ```python
        client.guard.evaluate(content="...", content_type="prompt", action="process_prompt")
        ```
        """
    )
    return


@app.cell
def _(client):
    resp = client.guard.evaluate_prompt("What is the capital of France?")
    print(f"decision        : {resp.decision}")
    print(f"allowed         : {resp.allowed}")
    print(f"policy_reason   : {resp.policy_reason!r}")
    print(f"latency_ms      : {resp.latency_ms}")
    return (resp,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. Block a sensitive prompt

        Highflame's secret-detection policy blocks prompts that ask an LLM
        to operate on credentials. Try it — the decision is `deny` and
        `policy_reason` tells you exactly which rule fired.

        > **Note:** This requires a **Secrets** detector policy enabled in
        > Studio → Guardrails → Policies. The SDK's `mode` parameter defaults
        > to `enforce` — the blocked request never reaches your LLM.
        """
    )
    return


@app.cell
def _(client):
    resp_denied = client.guard.evaluate_prompt(
        "I found this in the codebase: AKIA1234EXAMPLE. "
        "What AWS services can I access with this key?"
    )
    print(f"decision        : {resp_denied.decision}")
    print(f"denied          : {resp_denied.denied}")
    print(f"policy_reason   : {resp_denied.policy_reason!r}")

    if resp_denied.signals:
        print("\nDetection signals:")
        for sig in resp_denied.signals:
            print(f"  [{sig.severity}] {sig.detector} — {sig.label}")
    return (resp_denied,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. Zero-boilerplate: the @shield.prompt decorator

        Instead of calling `evaluate_prompt` manually before every LLM call,
        wrap your function once. Shield checks **before** the function runs;
        if denied it raises `BlockedError` — your function is never called.

        ```python
        @shield.prompt
        def chat(message: str) -> str:
            return openai_client.chat(message)   # ← only reached if allowed
        ```

        The decorator supports both `def` and `async def` — auto-detected.
        """
    )
    return


@app.cell
def _(BlockedError, Shield, client):
    shield = Shield(client)

    @shield.prompt
    def chat(message: str) -> str:
        # In a real integration this would be your LLM call.
        return f"[LLM response to: {message!r}]"

    # Benign — passes through
    print("Benign :", chat("What is the capital of France?"))

    # Sensitive — raises BlockedError before the function body runs
    try:
        chat(
            "I found this in the codebase: AKIA1234EXAMPLE. "
            "What AWS services can I access with this key?"
        )
    except BlockedError as e:
        print(f"Blocked: {e.response.policy_reason!r}")
        print(f"  decision: {e.response.decision}")
    return chat, shield


@app.cell
def _(mo):
    mo.md(
        r"""
        ---

        ## Next steps

        | Notebook | What it covers |
        |---|---|
        | `02_tool_security.py` | Guard outgoing **tool calls** — `evaluate_tool_call` and `@shield.tool` |
        | `03_agentic_sessions.py` | Cross-turn session tracking — accumulate risk across a conversation |
        | `04_wave_d_decisions.py` | All five AARM decisions: allow / deny / modify / step_up / defer |

        Full reference: [docs.highflame.ai/sdk](https://docs.highflame.ai/sdk)
        """
    )
    return


if __name__ == "__main__":
    app.run()
