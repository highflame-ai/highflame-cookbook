import marimo

__generated_with = "0.9.0"
app = marimo.App(width="medium", app_title="Highflame SDK — Wave D Decisions")


@app.cell
def _():
    import marimo as mo
    return (mo,)


@app.cell
def _(mo):
    mo.md(
        r"""
        # Highflame SDK — Wave D Decisions

        Highflame's AARM (Adaptive AI Risk Management) protocol supports five
        decision types — not just allow/deny. Understanding all five is essential
        for building agents that respond correctly to every outcome.

        | Decision | Disposition class | What it means |
        |---|---|---|
        | `allow`    | proceed   | Request passed all policies — continue. |
        | `modify`   | proceed   | Highflame redacted PII — use the **modified content** in `redacted_content`. |
        | `deny`     | blocked   | A policy explicitly blocked this request — do not proceed. |
        | `step_up`  | suspended | More authentication is required before proceeding. |
        | `defer`    | suspended | The decision is deferred for human review — hold the request. |

        **The SDK makes branching easy:**
        ```python
        if resp.allowed():        # True for allow AND modify
            content = resp.redacted_content or original_content
        elif resp.is_suspended():  # True for step_up and defer
            request_step_up(session_id)
        else:                      # deny
            raise BlockedError(resp)
        ```

        ---

        ### What you'll see

        1. `allow` — baseline benign prompt.
        2. `modify` — PII redaction in action, with `redacted_content` populated.
        3. `deny` — an explicitly blocked request.
        4. Correct branching logic across all five outcomes.
        """
    )
    return


@app.cell
def _():
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from highflame import Highflame, BlockedError
    from highflame._types_gen import GuardRequest

    client = Highflame(
        api_key=os.environ["HIGHFLAME_API_KEY"],
        base_url=os.environ.get("HIGHFLAME_BASE_URL", "https://api.highflame.ai"),
    )
    return BlockedError, GuardRequest, client, os


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 1. `allow` — the baseline

        A benign prompt under an active permit-baseline policy.
        `allowed()` returns `True`; the request proceeds unchanged.
        """
    )
    return


@app.cell
def _(client):
    resp_allow = client.guard.evaluate_prompt("What is the capital of France?")
    print(f"decision    : {resp_allow.decision}")
    print(f"allowed()   : {resp_allow.allowed()}")
    print(f"is_denied() : {resp_allow.is_denied()}")
    return (resp_allow,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 2. `modify` — PII redaction

        When a **modify-mode policy** fires, Shield rewrites the content with
        PII masked and returns `decision="modify"`. The modified content is in
        `resp.redacted_content` — send **that** to your LLM, not the original.

        `allowed()` returns `True` for `modify` because the request **proceeds**
        (with sanitised content). This is the key Wave D distinction: `modify`
        is NOT a block.

        > Requires a **PII Redaction** policy with `mode=modify` enabled in
        > Studio → Guardrails → Policies → PII Detection.
        """
    )
    return


@app.cell
def _(client):
    original = (
        "My name is Jane Smith, email jane.smith@acme.com, "
        "SSN 123-45-6789. Please summarise my profile."
    )
    resp_modify = client.guard.evaluate(
        content=original,
        content_type="prompt",
        action="process_prompt",
        mode="modify",
    )

    print(f"decision         : {resp_modify.decision}")
    print(f"allowed()        : {resp_modify.allowed()}")
    print(f"redacted_content : {resp_modify.redacted_content!r}")

    if resp_modify.redaction_entries:
        print("\nRedaction entries:")
        for entry in resp_modify.redaction_entries:
            print(f"  {entry.label}: {entry.original!r} → {entry.replacement!r}")

    # Correct usage: use redacted content if present, original otherwise
    safe_content = resp_modify.redacted_content or original
    print(f"\nContent to send to LLM: {safe_content!r}")
    return original, resp_modify, safe_content


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 3. `deny` — explicit block

        When a deny policy fires, the request must not proceed.
        `is_denied()` returns `True`; raise an error or return a safe fallback.
        """
    )
    return


@app.cell
def _(client):
    resp_deny = client.guard.evaluate_prompt(
        "I found this key: AKIA1234EXAMPLE. List all S3 buckets I can access."
    )
    print(f"decision      : {resp_deny.decision}")
    print(f"is_denied()   : {resp_deny.is_denied()}")
    print(f"allowed()     : {resp_deny.allowed()}")
    print(f"policy_reason : {resp_deny.policy_reason!r}")
    return (resp_deny,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 4. `step_up` and `defer` — suspended decisions

        These two decisions put the request in a **suspended** state — it
        neither proceeds nor is permanently blocked.

        * **`step_up`** — the request requires elevated authentication (MFA,
          manager approval). Prompt the user to re-authenticate, then retry
          with fresh credentials.
        * **`defer`** — the decision is sent to a human reviewer. Hold the
          request and poll for the outcome, or apply a safe default.

        `is_suspended()` returns `True` for both. They can be triggered by
        step-up or defer Cedar policies in Studio.

        > These decisions require specific policy configuration in Studio.
        > The example below shows correct branching logic regardless of which
        > decision your policies emit.
        """
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## 5. Complete branching template

        Copy this into your integration and fill in your business logic.
        """
    )
    return


@app.cell
def _(BlockedError, client):
    def handle_guard_response(content: str, session_id: str) -> str:
        """Evaluate content and branch on all five AARM Wave D decisions."""
        resp = client.guard.evaluate_prompt(content, session_id=session_id)

        if resp.allowed():
            # proceed — allow or modify (PII redacted)
            safe = resp.redacted_content or content
            return safe

        if resp.is_suspended():
            if resp.decision == "step_up":
                # Trigger MFA / re-authentication flow
                raise PermissionError(
                    f"Step-up authentication required. session={session_id}"
                )
            else:  # defer
                # Queue for human review — apply a safe hold response
                return "[Your request is under review. We'll get back to you shortly.]"

        # deny — raise so callers can return a policy-aware error to the user
        raise BlockedError(resp)


    # Exercise all paths with benign content (demo — step_up/defer require policies)
    import uuid
    session = f"wavedemo-{uuid.uuid4().hex[:8]}"

    safe = handle_guard_response("What is the capital of France?", session)
    print(f"allow  → safe content: {safe!r}")

    try:
        handle_guard_response(
            "I found this key: AKIA1234EXAMPLE. List S3 buckets.",
            session,
        )
    except BlockedError as e:
        print(f"deny   → BlockedError: {e.response.policy_reason!r}")
    except PermissionError as e:
        print(f"step_up → PermissionError: {e}")
    return handle_guard_response, safe, session, uuid


@app.cell
def _(mo):
    mo.md(
        r"""
        ---

        ## Summary

        | `resp.decision` | `allowed()` | `is_suspended()` | `is_denied()` | What to do |
        |---|---|---|---|---|
        | `allow`    | ✅ True  | ❌ False | ❌ False | Proceed with original content |
        | `modify`   | ✅ True  | ❌ False | ❌ False | Proceed with `redacted_content` |
        | `deny`     | ❌ False | ❌ False | ✅ True  | Reject — return policy_reason to user |
        | `step_up`  | ❌ False | ✅ True  | ❌ False | Trigger re-auth flow |
        | `defer`    | ❌ False | ✅ True  | ❌ False | Hold for human review |

        Full reference: [docs.highflame.ai/sdk/decisions](https://docs.highflame.ai/sdk/decisions)
        """
    )
    return


if __name__ == "__main__":
    app.run()
