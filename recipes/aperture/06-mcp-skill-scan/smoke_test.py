#!/usr/bin/env python3
"""CI smoke for 06 — MCP scan via ramparts.

A full MCP scan needs a live MCP server (or your IDE's configured servers), so CI
just confirms the ramparts CLI is installed and invokable. Locally, run scan.sh
against your own MCP servers.

Exit codes: 0 = pass, 1 = CLI present but errored, 2 = skipped (not installed).
"""
from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> int:
    if shutil.which("ramparts") is None:
        print("SKIP: ramparts CLI not installed (see https://github.com/highflame-ai/ramparts).")
        return 2

    result = subprocess.run(
        ["ramparts", "--help"], capture_output=True, text=True, timeout=30, check=False
    )
    if result.returncode != 0:
        print(f"FAIL ramparts --help exited {result.returncode}: {result.stderr.strip()}")
        return 1

    print("PASS ramparts CLI available")
    return 0


if __name__ == "__main__":
    sys.exit(main())
