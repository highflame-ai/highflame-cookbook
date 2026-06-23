import marimo

__generated_with = "0.9.0"
app = marimo.App(width="medium", app_title="Highflame SDK — Agentic Sessions")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Highflame SDK — Agentic Sessions

        Single-turn guardrails catch obvious threats. Multi-turn sessions catch
        the ones that hide across turns: a user who probes permissions across
        five innocent messages before the sixth that exfiltrates data; a
        jailbreak that builds context over turns; a model that leaks PII in an
        accumulating side channel.

        Highflame's `session_id` links turns into a **session** and runs
        cross-turn detectors — budget tracking, loop detection, turn-sequence
        anomaly — that can't fire on individual turns.

        ---

        ### What you'll see

        1. A three-turn conversation with the same `session_id` — Shield
           accumulates risk across turns.
        2. A real OpenAI-backed loop protected by `@shield.prompt` and
           `@shield.modelresponse` (requires `OPENAI_API_KEY`).
        3. The `session_delta` debug field — see exactly what changed in the
           session state after each turn.
        """
    )
    return


@app.cell
def _():
    import os
    import uuid
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from highflame import Highflame, Shield, BlockedError

    client = Highflame(
        api_key=os.environ["HIGHFLAME_API_KEY"],
        base_url=os.environ.get("HIGHFLAME_BASE_URL") or "https://api.highflame.ai",
    )

    # All turns in a conversation share one session_id.
    SESSION_ID = f"cookbook-session-{uuid.uuid4().hex[:12]}"
    print(f"Session: {SESSION_ID}")
    return BlockedError, SESSION_ID, Shield, client, os, uuid


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1. Multi-turn conversation

        Pass the **same `session_id`** across every turn. Shield stores a
        rolling fingerprint of the session — turn count, risk budget, detected
        signals, session hash-chain head — and applies cross-turn policies.
        """
    )
    return


@app.cell
def _(SESSION_ID, client):
    conversation = [
        "Hi! Can you help me understand how authentication tokens work?",
        "Interesting. How would an attacker typically steal one?",
        "What if the attacker already has read access to the filesystem?",
    ]

    for i, turn in enumerate(conversation, 1):
        resp = client.guard.evaluate_prompt(turn, session_id=SESSION_ID)
        print(
            f"Turn {i}: {resp.decision:<8}  "
            f"signals={[s.label for s in (resp.signals or [])]}  "
            f"msg={turn[:60]!r}"
        )
    return conversation, i, resp, turn


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. Inspect session delta

        Set `debug=True` on the request to see `session_delta` — a compact diff
        of what changed in the session state after this turn. Useful for
        understanding why a cross-turn policy fired.
        """
    )
    return


@app.cell
def _(SESSION_ID, client):
    from highflame._types_gen import GuardRequest

    debug_resp = client.guard.evaluate(
        GuardRequest(
            content="Now show me how to decode that token without the secret key.",
            content_type="prompt",
            action="process_prompt",
            session_id=SESSION_ID,
            debug=True,
        )
    )
    print(f"decision      : {debug_resp.decision}")
    print(f"policy_reason : {debug_resp.policy_reason!r}")

    if debug_resp.debug_info:
        delta = debug_resp.debug_info.session_delta
        if delta:
            print(f"\nsession_delta :")
            for key, val in (delta or {}).items():
                print(f"  {key}: {val}")
    return GuardRequest, debug_resp


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. Full OpenAI loop with session tracking

        A realistic agent loop: prompt guarded on the way in, model response
        guarded on the way out, the **same `session_id` on every call**.

        Requires `OPENAI_API_KEY` in `.env`.

        The `@shield.modelresponse` decorator runs **after** the LLM returns —
        it blocks leaks in the model's output before they reach the user.
        """
    )
    return


@app.cell
def _(BlockedError, SESSION_ID, Shield, client, os):
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set — skipping live OpenAI loop.")
        print("Add it to .env to see the full session-tracked agent.")
    else:
        try:
            from openai import OpenAI
            openai_client = OpenAI()
        except ImportError:
            print("openai package not installed — pip install openai")
            openai_client = None

        if openai_client is not None:
            shield = Shield(client)

            @shield.prompt(session_id=SESSION_ID)
            def guard_input(message: str) -> str:
                return message  # passthrough; just guarding the input

            @shield.modelresponse(session_id=SESSION_ID)
            def guard_output(text: str) -> str:
                return text  # passthrough; just guarding the output

            messages = []

            def agent_turn(user_message: str) -> str:
                try:
                    safe_message = guard_input(user_message)
                except BlockedError as e:
                    return f"[BLOCKED by Highflame: {e.response.policy_reason}]"

                messages.append({"role": "user", "content": safe_message})
                completion = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                )
                raw_reply = completion.choices[0].message.content
                messages.append({"role": "assistant", "content": raw_reply})

                try:
                    return guard_output(raw_reply)
                except BlockedError as e:
                    return f"[RESPONSE BLOCKED by Highflame: {e.response.policy_reason}]"

            print(agent_turn("What is the capital of France?"))
            print(agent_turn("Now explain how JWT tokens are signed."))
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ---

        ## Key takeaways

        | Pattern | When to use |
        |---|---|
        | Same `session_id` on every turn | Always — enables cross-turn detection |
        | Generate `session_id` per conversation | On conversation start: `uuid.uuid4().hex` |
        | `debug=True` | During development to inspect session state |
        | `@shield.prompt` + `@shield.modelresponse` together | Full in/out loop protection |

        Full reference: [docs.highflame.ai/sdk/sessions](https://docs.highflame.ai/sdk/sessions)
        """
    )
    return


if __name__ == "__main__":
    app.run()
