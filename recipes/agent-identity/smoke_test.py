"""Smoke test for the agent-identity recipe: no AWS needed, only HIGHFLAME_API_KEY.

Registers a throwaway orchestrator and specialist, guards a prompt as the specialist
under a delegated credential, checks the credential both ways, deactivates the
orchestrator and confirms the delegated credential is then refused, and cleans up.
Exit 0 on success, 1 on failure, 2 when the key is absent (skip).

The static checks at the top need no credentials, so they run on every PR even
when the canary secrets are unset. They guard sdk#162: a notebook must not use
tokens.verify() as the gate at a trust boundary, because a local signature check
cannot see a revocation.
"""

import ast
import os
import pathlib
import sys
import uuid

from dotenv import load_dotenv

RECIPE_DIR = pathlib.Path(__file__).parent


def _notebook_code(path: pathlib.Path) -> str:
    """Every code cell in a notebook, concatenated and parseable as Python.

    IPython magics (`%pip install ...`) and shell escapes (`!ls`) are valid in a
    notebook and a SyntaxError to ast.parse, so drop those lines.
    """
    import json

    nb = json.loads(path.read_text(encoding="utf-8"))
    lines: list[str] = []
    for cell in nb["cells"]:
        if cell.get("cell_type") != "code":
            continue
        for line in "".join(cell["source"]).splitlines():
            if line.lstrip().startswith(("%", "!")):
                continue
            lines.append(line)
        lines.append("")
    return "\n".join(lines)


def _static_checks() -> None:
    """Assert no recipe gates a trust boundary on the revocation-blind call.

    The A2A front door in the swarm notebook is the trust boundary in this
    recipe: it decides whether to serve a request from a credential a caller
    handed over. It must call verify_active(). Reading claims for telemetry with
    verify() afterwards is fine, and is left alone.
    """
    swarm = RECIPE_DIR / "strands_swarm_a2a_agent_identity.ipynb"
    code = _notebook_code(swarm)

    # Locate the middleware class rather than grepping the whole file, so a
    # telemetry cell that legitimately calls verify() cannot mask a regression
    # here, and cannot trip this check either.
    tree = ast.parse(code)
    door = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name == "RequireHighflameCredential"
        ),
        None,
    )
    assert door is not None, "the A2A front-door middleware is gone from the swarm notebook"
    door_src = ast.unparse(door)

    assert "verify_active" in door_src, (
        "the A2A front door must gate on tokens.verify_active(). verify() is a local "
        "signature-and-claims check and cannot see a revocation, so a credential from a "
        "deactivated agent would be served (sdk#162)."
    )
    assert "tokens.verify(" not in door_src, (
        "the A2A front door still calls tokens.verify(). That is the unsafe pattern "
        "sdk#162 reported."
    )
    assert "TokenRevokedError" in door_src, (
        "the front door should distinguish a revoked credential from a malformed one, "
        "so an operator's revocation is visible in the logs (sdk#162)."
    )

    # The floor has to carry verify_active(), or the notebooks import a version
    # without it and fail at runtime instead of at install time.
    reqs = (RECIPE_DIR / "requirements.txt").read_text(encoding="utf-8")
    assert "highflame[strands,langgraph]>=0.3.25" in reqs, (
        "the highflame floor must be at least 0.3.25 — the release that adds "
        "tokens.verify_active()"
    )

    # The LangGraph notebook used to claim a deactivated agent's issued
    # credentials "age out within its own lifetime". They do not; deactivation
    # cascade-revokes the delegated subtree at once.
    lg = (RECIPE_DIR / "langgraph_agent_identity.ipynb").read_text(encoding="utf-8")
    assert "ages out within its own" not in lg, (
        "the LangGraph notebook claims a deactivated agent's credentials age out. "
        "Deactivation cascade-revokes them immediately."
    )

    print("OK: static checks passed (trust-boundary call, version floor, revocation claim)")


try:
    _static_checks()
except AssertionError as exc:
    print(f"FAIL: {exc}")
    sys.exit(1)
except Exception as exc:  # noqa: BLE001 — a broken check must red the build, not traceback
    print(f"FAIL: static checks could not run: {type(exc).__name__}: {exc}")
    sys.exit(1)

load_dotenv()
api_key = os.environ.get("HIGHFLAME_API_KEY")
if not api_key:
    print("SKIP: HIGHFLAME_API_KEY is not set (static checks above still ran)")
    sys.exit(2)

from highflame import Highflame
from highflame.zeroid import ToolScope, generate_keypair
from highflame.zeroid.errors import TokenRevokedError

# Imported, not used: this is what makes CI fail when the LangGraph notebook's
# dependencies break, since CI runs this file and never runs the notebooks.
from highflame.integrations.langgraph import HighflameMiddleware  # noqa: F401

admin = Highflame(api_key=api_key)
run_id = uuid.uuid4().hex[:6]
common = dict(
    identity_type="agent",
    trust_level="first_party",
    framework="strands",
    description="cookbook smoke test, safe to delete",
)
created = []
try:
    orchestrator = admin.agents.register(
        name="Smoke Orchestrator",
        external_id=f"smoke-orchestrator-{run_id}",
        sub_type="orchestrator",
        allowed_scopes=[ToolScope.READ, ToolScope.EXECUTE, "orders:read"],
        **common,
    )
    created.append(orchestrator.agent.id)
    private_key_pem, public_key_pem = generate_keypair()
    specialist = admin.agents.register(
        name="Smoke Specialist",
        external_id=f"smoke-specialist-{run_id}",
        sub_type="tool_agent",
        allowed_scopes=[ToolScope.READ, ToolScope.EXECUTE, "orders:read"],
        capabilities=["lookup_order"],
        public_key_pem=public_key_pem,
        **common,
    )
    created.append(specialist.agent.id)

    orchestrator_client = Highflame(api_key=orchestrator.api_key)
    delegated = orchestrator_client.tokens.delegate_to(
        wimse_uri=specialist.agent.wimse_uri,
        private_key_pem=private_key_pem,
        scope=f"{ToolScope.READ} {ToolScope.EXECUTE} orders:read",
    )
    verified = orchestrator_client.tokens.verify(delegated.access_token)
    assert verified.is_delegated(), "credential is not marked as delegated"
    assert verified.external_id == specialist.agent.external_id, "credential names the wrong agent"

    decision = Highflame(access_token=delegated.access_token).guard.evaluate_prompt(
        "What's the status of order 1042?", session_id=f"smoke-{run_id}"
    )
    attributed = decision.agent_identity.external_id if decision.agent_identity else None
    assert attributed == specialist.agent.external_id, f"decision attributed to {attributed!r}"
    # verify_active() agrees with verify() while the chain is live, and returns
    # the same identity, so it is a drop-in at a trust boundary.
    active = orchestrator_client.tokens.verify_active(delegated.access_token)
    assert active.jti == verified.jti, "verify_active() named a different credential"

    print(
        f"OK: decision={decision.decision} attributed to {attributed}, delegated by {verified.delegated_by()}"
    )

    # sdk#162: deactivating the orchestrator must kill the credential it
    # delegated, and both enforcement points must agree that it is dead.
    # Deactivate here rather than in the finally block so the cleanup below
    # stays idempotent.
    admin.agents.delete(orchestrator.agent.id)
    created.remove(orchestrator.agent.id)

    # The local check still passes. That is correct for a local check, and it is
    # the behavior #162 reported — asserted here so a future change that makes
    # verify() do a network call does not pass unnoticed.
    still_verifies = orchestrator_client.tokens.verify(delegated.access_token)
    assert still_verifies.jti == verified.jti

    try:
        orchestrator_client.tokens.verify_active(delegated.access_token)
    except TokenRevokedError as exc:
        print(
            "OK: after deactivating the orchestrator, verify_active() refused the "
            f"delegated credential (revoked {exc.revoked_jti or 'credential'}, "
            f"reason {exc.revoke_reason or 'unset'}) while verify() still passed"
        )
    else:
        raise AssertionError(
            "verify_active() accepted a credential delegated from a deactivated agent. "
            "That is the sdk#162 regression."
        )
except Exception as exc:  # noqa: BLE001
    print(f"FAIL: {type(exc).__name__}: {exc}")
    sys.exit(1)
finally:
    for identity_id in created:
        try:
            admin.agents.delete(identity_id)
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup skipped for {identity_id}: {exc}")
