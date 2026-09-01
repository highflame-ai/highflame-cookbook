#!/usr/bin/env python3
"""Smoke test for the ODIS recipe.

Contract shared by every cookbook recipe:
    exit 0 = passed, 1 = a real failure, 2 = skipped (missing configuration).

Runs the conformance harness and fails the build if any ODIS check regresses.
A SKIP inside the harness (e.g. no Cedar policies enabled in the target tenant)
does not fail the build — a missing tenant-side setup step is not a platform
regression.
"""

from __future__ import annotations

import sys

from odis_client import ODISRecipeError, load_config


def main() -> int:
    cfg = load_config()
    if not cfg.can_provision:
        print(
            "SKIP: set HIGHFLAME_REGISTRAR_TOKEN (a Bearer token with the "
            "nhi:manage scope) or HIGHFLAME_INTERNAL_SERVICE_SECRET to run this "
            "recipe. See .env.example.",
            file=sys.stderr,
        )
        return 2

    from odis_conformance import FAIL, PASS, SKIP, Harness

    try:
        harness = Harness(cfg)
    except ODISRecipeError as exc:
        print(f"SKIP: cannot reach the identity plane — {exc}", file=sys.stderr)
        return 2

    try:
        for name, stage in (
            ("Layer 1", harness.layer1),
            ("Attestation", harness.attestation_gate),
            ("Layer 2", harness.layer2),
            ("Async auth", harness.async_authorization),
            ("Layer 3", harness.layer3),
        ):
            try:
                stage()
            except ODISRecipeError as exc:
                print(f"FAIL: {name} could not complete — {exc}", file=sys.stderr)
                return 1
            except Exception as exc:  # noqa: BLE001
                print(f"FAIL: {name} raised {type(exc).__name__}: {exc}", file=sys.stderr)
                return 1
    finally:
        # Nightly CI runs this against a canary tenant; without retirement it
        # would accumulate thousands of orphaned agent identities a year.
        retired, failed = harness.cp.retire_all_created()
        print(f"retired {retired} demo identities"
              + (f" ({failed} failed)" if failed else ""), file=sys.stderr)

    failures = [c for c in harness.checks if c.status == FAIL]
    passes = [c for c in harness.checks if c.status == PASS]
    skips = [c for c in harness.checks if c.status == SKIP]

    for c in failures:
        print(f"FAIL {c.req}: {c.title} — {c.evidence}", file=sys.stderr)
    for c in skips:
        print(f"skip {c.req}: {c.evidence}", file=sys.stderr)

    print(f"{len(passes)} ODIS checks passed, {len(failures)} failed, {len(skips)} skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
