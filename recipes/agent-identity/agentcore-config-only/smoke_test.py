"""Smoke test for the AgentCore configuration-only recipe.

The static checks need no credentials, so they run on every change: every script
compiles, the agent imports nothing from Highflame, and every setting a script
reads is documented in .env.example.

The live check invokes a deployed runtime (SMOKE_RUNTIME) once for each outcome
the recipe promises, and fails if any outcome changes. It needs your AWS
credentials, a runtime deployed with deploy.py, and the Highflame setup in the
README, including the policy that blocks export_customers. Without them it skips.

Exit 0 on success, 1 on failure, 2 when the live check cannot run (skip).
"""

from __future__ import annotations

import os
import pathlib
import py_compile
import re
import sys

from dotenv import load_dotenv

RECIPE_DIR = pathlib.Path(__file__).resolve().parent
SCRIPTS = ["deploy.py", "smoke_test.py", "agent/agent_app.py", "agent/acme_crm_server.py"]

# (name, prompt, check). Each check gets the agent's reply and returns "" on a pass,
# or what went wrong.
CASES = [
    ("allowed model and tool call", "Find the customer named Northwind.",
     lambda r: "" if "search_customers" in r.get("tools_called", {}) and "C-1001" in r.get("answer", "")
     else "expected search_customers to run and the answer to name C-1001"),
    ("guardrail blocks a secret in the prompt",
     "Save this note on Northwind: our AWS key is AKIAIOSFODNN7EXAMPLE and the secret is "
     "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
     lambda r: "" if "blocked" in (r.get("answer", "") + r.get("error", "")).lower() and not r.get("tools_called")
     else "expected the Highflame guardrail to block the prompt"),
    ("policy blocks a tool call", "Export every customer record.",
     lambda r: "" if "blocked by security policy" in r.get("answer", "") and "export_customers" not in r.get("tools_called", {})
     else "expected the policy to block export_customers before it ran"),
]


def static_checks() -> None:
    documented = (RECIPE_DIR / ".env.example").read_text()
    for name in SCRIPTS:
        path = RECIPE_DIR / name
        py_compile.compile(str(path), doraise=True)
        source = path.read_text()
        read = set(re.findall(r'setting\("([A-Z_]+)"', source))
        read |= set(re.findall(r'os\.environ(?:\.get\(|\[)"([A-Z_]+)"', source))
        for setting in sorted(read):
            assert re.search(rf"^#? ?{setting}=", documented, re.M), (
                f"{name} reads {setting}, which .env.example does not document")
    for name in ("agent/agent_app.py", "agent/acme_crm_server.py"):
        source = (RECIPE_DIR / name).read_text()
        assert not re.search(r"^\s*(from|import)\s+highflame", source, re.M), (
            f"{name} imports a Highflame package; the agent must be configuration only")
    requirements = (RECIPE_DIR / "agent" / "requirements.txt").read_text()
    assert not re.search(r"^\s*highflame", requirements, re.M | re.I), (
        "agent/requirements.txt lists a Highflame package; the agent must be configuration only")


def live_checks() -> int:
    load_dotenv(RECIPE_DIR / ".env")
    runtime = os.environ.get("SMOKE_RUNTIME", "").strip()
    if not runtime:
        print("SKIP (live): set SMOKE_RUNTIME in .env to a runtime deployed with deploy.py")
        return 2
    try:
        sys.path.insert(0, str(RECIPE_DIR))
        import deploy  # noqa: PLC0415 (needs AWS credentials, so only in the live check)
    except Exception as e:  # noqa: BLE001
        print(f"SKIP (live): no AWS credentials or settings: {e}")
        return 2

    failed = 0
    for name, prompt, check in CASES:
        reply = deploy.invoke(runtime, prompt)
        problem = check(reply)
        if problem:
            failed += 1
            print(f"FAIL {name}: {problem}\n     reply: {reply}")
        else:
            print(f"PASS {name}")
    return 1 if failed else 0


def main() -> int:
    try:
        static_checks()
    except (AssertionError, py_compile.PyCompileError) as e:
        print(f"FAIL (static): {e}")
        return 1
    print("static checks passed")
    return live_checks()


if __name__ == "__main__":
    sys.exit(main())
