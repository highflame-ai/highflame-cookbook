# Contributing

## Repo layout

Each `recipes/<name>/` directory is a self-contained recipe: a README (Studio setup +
runnable proof), one or more scripts, a `smoke_test.py`, `requirements.txt`, and a
`.env.example`.

## Conventions

- **Secrets via env only.** Every recipe reads credentials from environment variables and
  ships a `.env.example`. Never commit a real key.
- **Runs against production by default.** Scripts target the live Highflame SaaS
  (`*.highflame.ai`) and read credentials from the environment. With no key set they exit
  early, so nothing runs against a real tenant by accident.
- **Every recipe ships a `smoke_test.py`** — the fastest way to confirm keys and policies
  are wired correctly end to end, and the entrypoint CI uses.
- **Recipes that use the SDK check it before they run.** `requirements.txt` holds the
  floor (`highflame>=X`, the first release with every SDK call the recipe makes) and may
  hold `# highflame: tested-with X`. A copy of `recipes/sdk/preflight.py` sits in the
  recipe directory, and every entry point calls it before importing `highflame`:
  `import preflight; preflight.check()` at the top of a script, in its own first cell
  of a marimo notebook, and right after `%pip install` in a Jupyter notebook. An older
  SDK then stops the recipe on that line, naming the fix, instead of failing partway
  through. Set `HIGHFLAME_PREFLIGHT=off` to skip it when you run against an SDK built
  from source. Leave it out of a module that something else loads, like a LiteLLM
  guardrail or an app deployed to AgentCore.

## CI

[`.github/workflows/smoke.yml`](.github/workflows/smoke.yml) discovers every recipe's
`smoke_test.py` (`find recipes -name smoke_test.py`) and runs it on change and on a nightly
schedule. Each test exits `0` on success, `1` on a real failure, and `2` (skip) when its
credentials aren't present — so the build stays green until repo secrets
(`HIGHFLAME_API_KEY` plus any provider keys) are configured, after which the scheduled run
exercises them against a canary tenant. Until then, a green build has run no recipe.

The smoke job runs twice: with the newest SDK, and with each recipe's floor pinned
exactly, so a floor that is set too low fails. Both runs treat an SDK deprecation as an
error, so a recipe fails before a name it calls is removed. That needs an SDK that
exports `HighflameDeprecationWarning`; with an older one, the preflight says so and skips
the check. A separate job runs the preflight self-test and checks that every SDK recipe's
`preflight.py` is identical to `recipes/sdk/preflight.py`. Edit that one and copy it to
the others.

## Adding a recipe

1. Create `recipes/<name>/` with a README, the runnable script(s), `smoke_test.py`,
   `requirements.txt`, and `.env.example`.
2. Keep the README **customer-facing**: lead with the value, give the exact Studio
   click-path, then the runnable proof. Avoid internal service/detector names — say what
   the customer gets ("Highflame blocks the request"), not how it's routed internally.
3. Make `smoke_test.py` skip (exit `2`) cleanly when keys are absent.
4. If the recipe uses the SDK, copy in `recipes/sdk/preflight.py` and call it from every
   entry point (see Conventions).
