"""Self-test for recipes/*/preflight.py. Run: python .github/scripts/test_preflight.py"""

import contextlib
import importlib.util
import io
import os
import pathlib
import tempfile
from importlib.metadata import PackageNotFoundError

root = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("preflight", root / "recipes/sdk/preflight.py")
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)


def run(reqs, versions):
    def fake(name):
        if name not in versions:
            raise PackageNotFoundError(name)
        return versions[name]

    pf.installed = fake
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(reqs)
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            pf.check(f.name)
        return "ok", err.getvalue()
    except SystemExit as e:
        return "stop", str(e)
    finally:
        os.unlink(f.name)


assert pf._v("0.12.0") > pf._v("0.9.0")
assert pf._v("1.0") == pf._v("1.0.0") == pf._v("1.0.0rc1")

# floor met, tested-with equal: silent
assert run("highflame>=0.7.0\n# highflame: tested-with 0.12.0\n", {"highflame": "0.12.0"}) == ("ok", "")
# extras and comments on the line
assert run("highflame[strands]>=0.6.0   # why\n", {"highflame": "0.6.0"})[0] == "ok"
# SDK below the floor stops and names both versions
status, msg = run("highflame>=0.7.0\n", {"highflame": "0.3.23"})
assert status == "stop" and "0.3.23" in msg and ">=0.7.0" in msg, msg
# strict > floor
assert run("highflame>0.5.0\n", {"highflame": "0.5.0"})[0] == "stop"
# SDK missing stops
assert run("highflame>=0.7.0\n", {})[0] == "stop"
# other package missing: fine (often optional); too old: warn, not stop
assert run("highflame>=0.7.0\nmarimo>=0.9.0\n", {"highflame": "0.7.0"}) == ("ok", "")
status, msg = run("highflame>=0.7.0\nlitellm>=1.96.0\n", {"highflame": "0.7.0", "litellm": "1.50.0"})
assert status == "ok" and "litellm 1.50.0" in msg, msg
# newer minor than tested-with warns below 1.0; a newer patch does not
assert "newer than this recipe was tested" in run("highflame>=0.7.0\n# highflame: tested-with 0.12.0\n", {"highflame": "0.13.0"})[1]
assert run("highflame>=0.7.0\n# highflame: tested-with 0.12.0\n", {"highflame": "0.12.4"}) == ("ok", "")
# from 1.0, only a newer major warns
assert run("highflame>=1.0.0\n# highflame: tested-with 1.2.0\n", {"highflame": "1.9.0"}) == ("ok", "")
assert "newer" in run("highflame>=1.0.0\n# highflame: tested-with 1.2.0\n", {"highflame": "2.0.0"})[1]
# no highflame requirement at all: nothing to check
assert run("python-dotenv>=1.0\n", {}) == ("ok", "")
# a kernel still holding an older imported highflame stops
import sys, types  # noqa: E401,E402
sys.modules["highflame"] = types.SimpleNamespace(__version__="0.6.0")
status, msg = run("highflame>=0.6.0\n", {"highflame": "0.12.0"})
assert status == "stop" and "Restart the kernel" in msg, msg
del sys.modules["highflame"]
# the escape hatch skips everything
os.environ["HIGHFLAME_PREFLIGHT"] = "off"
assert run("highflame>=0.7.0\n", {"highflame": "0.3.0"}) == ("ok", "")
del os.environ["HIGHFLAME_PREFLIGHT"]

print("preflight self-test: ok")
