"""Create this recipe's policies in a Highflame project.

The Cedar in ``policies/*.cedar`` is the single source of truth — this script
reads those files and posts them, so what runs in your tenant is byte-for-byte
what is reviewed in the repo.

    python create_policies.py --dry-run     # show what would be created
    python create_policies.py               # create them
    python create_policies.py --mode monitor  # create without enforcing

Credentials
-----------
Policy creation goes through Admin, which does NOT accept a Shield service key
(``zid_sk_…``). Admin's API-key path resolves account credentials from its own
store, and a Shield key is not one — it returns:

    400 {"error": "Missing or invalid account credentials"}

You need a **Studio session token** (Clerk). Get one from a logged-in Studio
tab: DevTools → Network → any ``/v2/admin/…`` request → the ``Authorization:
Bearer …`` header. Then:

    export HIGHFLAME_ADMIN_TOKEN='eyJ…'
    export HIGHFLAME_ADMIN_URL='https://control-dev.highflame.dev'

The same flow works against a customer tenant under Clerk impersonation — the
token carries the impersonated org, so the policies land in their account.

Recommended split for a demo tenant
-----------------------------------
    python create_policies.py --only 01,02 --mode enforce
    python create_policies.py --only 03    --mode monitor

Policy 03 goes in **monitor** on purpose. Its second rule blocks *unverified*
agents from sensitive tools, and a plain service key authenticates as
``trust_level="unverified"`` until the agent is registered and adopted. In
enforce mode it therefore blocks every sensitive tool call — including the
clean-session control the walkthrough uses to show that ordinary use still
works. In monitor mode it still records ``actual_decision="deny"`` on every
event, so Observatory shows exactly what it would have stopped, and the
before/after contrast survives.

Raise the agent's trust level (register + adopt it in Studio) and you can move
03 to enforce.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

POLICY_DIR = Path(__file__).parent / "policies"

# filename → (policy name, category, what it is)
CATALOG: dict[str, tuple[str, str, str]] = {
    "00_baseline.cedar": (
        "Permit Baseline",
        "organization",
        "Default-allow floor. SKIP if the project already has one.",
    ),
    "01_trajectory_escalation.cedar": (
        "Multi-Turn Trajectory Escalation",
        "security",
        "Blocks a conversation whose trajectory is an attack.",
    ),
    "02_session_accumulation.cedar": (
        "Session Risk Accumulation",
        "agent-security",
        "Blocks the tool call the conversation was working toward.",
    ),
    "03_dual_attribution.cedar": (
        "Dual Attribution",
        "agent-identity",
        "Requires an accountable principal behind privileged agent actions.",
    ),
}


def load_policies(skip_baseline: bool) -> list[tuple[str, str, str, str]]:
    """Return (filename, policy_name, category, cedar_text)."""
    out = []
    for filename, (name, category, _) in CATALOG.items():
        if skip_baseline and filename.startswith("00_"):
            continue
        path = POLICY_DIR / filename
        if not path.exists():
            raise SystemExit(f"missing policy file: {path}")
        out.append((filename, name, category, path.read_text()))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print, do not create")
    parser.add_argument(
        "--mode",
        default="enforce",
        choices=("enforce", "monitor", "alert"),
        help="enforcement mode (default: enforce)",
    )
    parser.add_argument(
        "--with-baseline",
        action="store_true",
        help="also create the baseline permit (skip it if the project already has one)",
    )
    parser.add_argument(
        "--only",
        default="",
        help="comma-separated file prefixes, e.g. --only 01,02. Use this to give "
        "policy 03 a different mode from 01/02 — see the note below.",
    )
    args = parser.parse_args()

    policies = load_policies(skip_baseline=not args.with_baseline)
    if args.only:
        wanted = tuple(p.strip() for p in args.only.split(",") if p.strip())
        policies = [p for p in policies if p[0].startswith(wanted)]
        if not policies:
            raise SystemExit(f"--only {args.only!r} matched no policy files")

    if args.dry_run:
        print(f"Would create {len(policies)} policies in mode={args.mode}:\n")
        for filename, name, category, cedar in policies:
            rules = [ln for ln in cedar.splitlines() if ln.strip().startswith("@id(")]
            print(f"  {name}  [{category}]  ({filename})")
            for r in rules:
                print(f"      {r.strip()}")
            print()
        return 0

    admin_url = os.getenv("HIGHFLAME_ADMIN_URL", "https://control-dev.highflame.dev").rstrip("/")
    token = os.getenv("HIGHFLAME_ADMIN_TOKEN", "").strip()
    if not token:
        print(
            "HIGHFLAME_ADMIN_TOKEN is not set — see this file's docstring for how to get "
            "a Studio session token. Run with --dry-run to preview without one.",
            file=sys.stderr,
        )
        return 2

    created, failed = 0, 0
    with httpx.Client(timeout=45.0) as client:
        for filename, name, category, cedar in policies:
            body = {
                "policy_name": name,
                "policy_type": "cedar",
                "category": category,
                "content": cedar,
                "description": f"Highflame cookbook — deep-context recipe ({filename}).",
                "mode": args.mode,
                "labels": {"product": "guardrails", "source": "highflame-cookbook/deep-context"},
            }
            # account_id / project_id / created_by are injected by Admin from
            # the token's claims — never send them, they would be ignored.
            resp = client.post(
                f"{admin_url}/v2/admin/policy",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code in (200, 201):
                created += 1
                print(f"  created  {name}")
            elif resp.status_code == 409:
                print(f"  exists   {name} (already active — PATCH it instead of re-creating)")
            else:
                failed += 1
                print(f"  FAILED   {name}: {resp.status_code} {resp.text[:300]}")

    print(f"\ncreated={created} failed={failed}")
    if created:
        print(
            "\nVerify they are live in Shield (not just stored in Admin):\n"
            "    python -c \"from deep_context import connect; "
            'print(connect().debug.policies())"'
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
