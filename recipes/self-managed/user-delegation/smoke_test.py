"""Smoke test for the user-delegation recipe.

The static checks need no credentials, so they run on every change: every
script compiles, and every setting a script reads is documented in .env.example.

The live check runs both flows end to end. It needs a customer-managed
Highflame deployment, the Okta setup in the README, and one interactive
sign-in first (python signin.py). It never opens a browser: it reuses the saved
sign-in. Without those it skips.

Exit 0 on success, 1 on failure, 2 when the live check cannot run (skip).
"""

from __future__ import annotations

import os
import pathlib
import py_compile
import re
import subprocess
import sys

from dotenv import load_dotenv

RECIPE_DIR = pathlib.Path(__file__).resolve().parent
SCRIPTS = ["common.py", "signin.py", "id_token_flow.py", "id_jag_flow.py"]
LIVE_SETTINGS = ["HIGHFLAME_IDENTITY_URL", "MCP_SERVER_URL", "AGENT_PRIVATE_KEY_PATH",
                 "OKTA_ORG_URL", "OKTA_CLIENT_ID"]


def static_checks() -> None:
    documented = (RECIPE_DIR / ".env.example").read_text()
    for name in SCRIPTS:
        py_compile.compile(str(RECIPE_DIR / name), doraise=True)
        source = (RECIPE_DIR / name).read_text()
        read = set(re.findall(r'setting\("([A-Z_]+)"', source))
        read |= set(re.findall(r'os\.environ(?:\.get\(|\[)"([A-Z_]+)"', source))
        for setting in sorted(read):
            assert re.search(rf"^#? ?{setting}=", documented, re.M), (
                f"{name} reads {setting}, which .env.example does not document")


def main() -> int:
    try:
        static_checks()
    except (AssertionError, py_compile.PyCompileError) as e:
        print(f"FAIL (static): {e}")
        return 1
    print("static checks passed")

    load_dotenv(RECIPE_DIR / ".env")
    missing = [name for name in LIVE_SETTINGS if not os.environ.get(name)]
    if missing:
        print(f"SKIP live check: set {', '.join(missing)} (see .env.example)")
        return 2
    if not (RECIPE_DIR / ".tokens" / "refresh_token").exists():
        print("SKIP live check: sign in once first with `python signin.py`")
        return 2

    failed = []
    for script in ["id_token_flow.py", "id_jag_flow.py"]:
        print(f"\n--- {script}")
        if subprocess.run([sys.executable, script], cwd=RECIPE_DIR).returncode != 0:
            failed.append(script)
    if failed:
        print(f"\nFAIL: {', '.join(failed)}")
        return 1
    print("\nPASS: both flows got a Highflame token for the person and listed the MCP server's tools")
    return 0


if __name__ == "__main__":
    sys.exit(main())
