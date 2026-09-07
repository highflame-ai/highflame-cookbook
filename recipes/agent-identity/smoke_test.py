"""Smoke test for the agent-identity recipe: no AWS needed, only HIGHFLAME_API_KEY.

Registers a throwaway orchestrator and specialist, guards a prompt as the specialist
under a delegated credential, verifies that credential, and cleans up.
Exit 0 on success, 1 on failure, 2 when the key is absent (skip).
"""

import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("HIGHFLAME_API_KEY")
if not api_key:
    print("SKIP: HIGHFLAME_API_KEY is not set")
    sys.exit(2)

from highflame import Highflame
from highflame.zeroid import ToolScope, generate_keypair

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
    print(
        f"OK: decision={decision.decision} attributed to {attributed}, delegated by {verified.delegated_by()}"
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
