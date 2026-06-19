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

## CI

[`.github/workflows/smoke.yml`](.github/workflows/smoke.yml) discovers every recipe's
`smoke_test.py` (`find recipes -name smoke_test.py`) and runs it on change and on a nightly
schedule. Each test exits `0` on success, `1` on a real failure, and `2` (skip) when its
credentials aren't present — so the build stays green until repo secrets
(`HIGHFLAME_API_KEY` plus any provider keys) are configured, after which the scheduled run
exercises them against a canary tenant.

## Adding a recipe

1. Create `recipes/<name>/` with a README, the runnable script(s), `smoke_test.py`,
   `requirements.txt`, and `.env.example`.
2. Keep the README **customer-facing**: lead with the value, give the exact Studio
   click-path, then the runnable proof. Avoid internal service/detector names — say what
   the customer gets ("Highflame blocks the request"), not how it's routed internally.
3. Make `smoke_test.py` skip (exit `2`) cleanly when keys are absent.
