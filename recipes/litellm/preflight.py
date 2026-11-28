"""Check this recipe's dependencies before it runs.

Run it first, before importing highflame:

    import preflight; preflight.check()

It reads requirements.txt next to this file:

    highflame>=0.7.0                 the floor; an older SDK stops the recipe
    # highflame: tested-with 0.12.0  a newer SDK minor gets a warning

Standard library only, and it never imports highflame before the version
check: the case it exists for is an SDK too old to have any helper. Every
recipe carries an identical copy (CI checks that), so a recipe still works
when its directory is copied on its own. See the client-server contracts
ADR in highflame-architecture, D11.
"""

import os
import re
import sys
import warnings
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed

_FLOOR = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?\s*(>=|>)\s*([0-9][^\s,;#]*)")
_TESTED = re.compile(r"^\s*#\s*highflame:\s*tested-with\s+(\S+)")


def _v(s):
    # ponytail: release numbers only ("0.12.0rc1" reads as 0.12.0). Use
    # packaging.version if a recipe ever pins a pre-release.
    parts = [int(p) for p in re.findall(r"\d+", s.split("+")[0])[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def _say(msg):
    print(f"preflight: {msg}", file=sys.stderr)


def check(requirements=None):
    # For SDK developers: a build from source can carry a new method while
    # still reporting the previous release number.
    if os.environ.get("HIGHFLAME_PREFLIGHT") == "off":
        return
    path = requirements or os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    fix = f"pip install -U -r {path}"
    tested = None
    sdk = None
    for line in open(path, encoding="utf-8"):
        m = _TESTED.match(line)
        if m:
            tested = m.group(1)
            continue
        m = _FLOOR.match(line)
        if not m:
            continue
        name, op, floor = m.groups()
        try:
            have = installed(name)
        except PackageNotFoundError:
            if name == "highflame":
                raise SystemExit(f"preflight: highflame is not installed. Run: {fix}")
            continue  # other packages are often optional for one entry point
        if name == "highflame":
            sdk = have
        ok = _v(have) >= _v(floor) if op == ">=" else _v(have) > _v(floor)
        if ok:
            continue
        msg = f"{name} {have} is installed; this recipe needs {name}{op}{floor}. Run: {fix}"
        if name == "highflame":
            raise SystemExit(f"preflight: {msg}")
        _say(msg)

    # A notebook kernel that imported highflame before an upgrade keeps the old
    # module, though the package metadata already reports the new version.
    loaded = getattr(sys.modules.get("highflame"), "__version__", sdk)
    if sdk and loaded != sdk:
        raise SystemExit(f"preflight: highflame {sdk} is installed but {loaded} is loaded. Restart the kernel.")

    if sdk and tested:
        # 0.x minors can break, so compare major.minor below 1.0 and major above.
        n = 2 if _v(tested)[0] == 0 else 1
        if _v(sdk)[:n] > _v(tested)[:n]:
            _say(
                f"highflame {sdk} is newer than this recipe was tested with ({tested}). "
                f"If something fails, try: pip install 'highflame=={tested}'"
            )

    if sdk and os.environ.get("HIGHFLAME_PREFLIGHT_STRICT"):
        # CI only: an SDK deprecation fails the run before the name is removed.
        # Safe to import now that the version is known to be new enough.
        import highflame

        cls = getattr(highflame, "HighflameDeprecationWarning", None)
        if cls:
            warnings.simplefilter("error", cls)
        else:
            _say("this SDK has no HighflameDeprecationWarning; deprecations are not checked")
