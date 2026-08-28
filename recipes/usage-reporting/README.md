# Usage, cost & productivity reporting

Studio already shows what your agents cost and what they shipped. That does
not help when finance wants last month's number in a spreadsheet, or when you
want to ask a model which developers are burning tokens on side projects.

This recipe pulls the same numbers as JSON, JSON Lines, or CSV, on whatever
schedule you set.

**What you get**

| Question | Script |
| --- | --- |
| What did every developer actually send? | `export_events.py` |
| What are we spending, by model and by product? | `usage_report.py --report cost` |
| Who is using the most tokens, and who is getting blocked? | `usage_report.py --report usage` |
| What did the AI sessions ship (commits, PRs, issues closed)? | `usage_report.py --report productivity` |

---

## Set up once in Studio

1. Sign in at [studio.highflame.ai](https://studio.highflame.ai).
2. Go to **Settings → API Keys**.
3. Select **Create key**, name it something like `reporting`, and copy the
   `zid_sk_…` value. You only see it once.

```bash
cp .env.example .env      # paste your key into HIGHFLAME_API_KEY
pip install -r requirements.txt
```

Both scripts load `.env` when `python-dotenv` is installed. Without it they
read the same variables from the environment, so
`export HIGHFLAME_API_KEY=zid_sk_…` works just as well.

---

## Run the proof

```bash
python smoke_test.py
```

It mints a token, prints the scope that token is bound to, and runs one line
per report:

```
PASS token minted, scope account_id=757038846364 project_id=e6ae415d-…
PASS event export returned 5 prompt event(s)
PASS cost report, total $412.50
PASS usage report, 12 active developer(s)
PASS productivity report, 148 commit(s)
```

---

## Export events

`export_events.py` writes one row per event.

```bash
# Everything in the last 24 hours, as JSON Lines.
python export_events.py

# Prompts only, tool calls dropped, for the last 30 days, as CSV.
python export_events.py --prompts-only --since 30d --format csv -o prompts.csv

# One developer, blocked events only.
python export_events.py --user-id user_39x4SRPR9kKGvvQVNYFlcSmWwCE --decision deny
```

**Filters:** `--product`, `--service`, `--event-type`, `--decision`, `--mode`,
`--severity`, `--threat-category`, `--session-id`, `--user-id`, `--agent-id`,
`--source-ide`, `--search`, `--has-threats`.

Two of these are easy to mix up:

- `--decision` takes `allow`, `deny`, `modify`, `step_up`, or `defer`. That is
  what the policy decided. `monitor` is **not** a decision. It is a mode, so
  use `--mode monitor`.
- `--search` matches tool names and user names. It does **not** search prompt
  text, so an empty result is not evidence that a phrase was never sent.

**Window:** `--since 90m|24h|30d`, or an explicit `--start` and `--end` in
RFC3339. `--since` counts back from `--end` when you give one, so
`--end 2026-01-01T00:00:00Z --since 30d` reads December rather than a window
that ends before it starts.

**Output:** `--format jsonl` is the default and keeps every field, including
detector scores and labels. `--format csv` writes 33 flat columns for a
spreadsheet.

A prompt is an event with no tool call attached. `--prompts-only` asks the
server for prompt events, then drops any row that still carries a tool name.

---

## Pull the reports

`usage_report.py` returns aggregates rather than rows.

```bash
# Everything for the last 30 days, human-readable.
python usage_report.py --since 30d

# One JSON document to hand to an LLM.
python usage_report.py --since 30d --format json -o report.json

# Just the per-developer breakdown, last week.
python usage_report.py --report usage --since 7d
```

| Report | Contents |
| --- | --- |
| `cost` | Total spend and detections, broken out by product and by model, with request counts, token counts, and latency |
| `usage` | Per developer: events, tokens, threat events, blocked events, time spent. Plus totals and an active-developer count |
| `productivity` | Commits, PRs created, PRs merged, PRs closed, issues closed, lines added and removed, shipping sessions, active developers. Broken out by repo and by developer |

`--report all` is the default.

**Read the `INCOMPLETE` lines.** Long tables get capped, either by the server
or by the script at 25 repos and 200 developers. Any list that was cut is named
in the report header, and in `meta.truncated` in the JSON. A capped "By
developer" table also under-counts `active_developers`. Treat those lines as a
correctness warning, not a footnote.

**`shipping_sessions` and `total_sessions` are not two halves of one ratio.**
`shipping_sessions` counts sessions that produced git activity. `total_sessions`
counts every session the guard saw, across products and across traffic that was
never coding work. Dividing one by the other does not give you a shipping rate.
On a real tenant it comes out at 0.02%. Both counts are in the output. Scope
them to the same traffic before you compare them.

### Feeding a report to an LLM

The JSON document is self-describing and fits in one prompt. This is the shape
teams use to ask "is anyone driving unnecessary cost?":

```bash
python usage_report.py --since 30d --format json -o report.json

# Then hand report.json to your model of choice with a prompt such as:
#   "Here is 30 days of AI usage for our engineering org. Flag any developer
#    whose token spend is out of line with what they shipped, and say why."
```

---

## How the API works

Both scripts do the same two steps. Copy them into your own tooling if you
prefer.

**1. Exchange your API key for a token.**

```bash
curl -s -X POST https://auth.highflame.ai/oauth2/token \
  -d 'grant_type=api_key' \
  -d "api_key=$HIGHFLAME_API_KEY"
# -> {"access_token":"eyJ…", …}
```

**2. Call the reporting API with that token.**

```bash
curl -s "https://api.highflame.ai/v1/obs/events?start=2026-08-01T00:00:00Z&end=2026-08-28T00:00:00Z&limit=100" \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl -s "https://api.highflame.ai/v1/obs/costs/intelligence?start=2026-08-01T00:00:00Z&end=2026-08-28T00:00:00Z" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

The reporting API does not accept the `zid_sk_…` key directly. Step 1 is
required.

These scripts use plain HTTP rather than the Highflame SDK. The SDK covers
Shield today (`guard`, `detect`, `detectors`, `debug`, `identity`), and has no
reporting namespace, so there is nothing to install beyond the standard
library.

For anything the fixed endpoints do not cover, `POST /v1/obs/query` runs a
query against a named view. `GET /v1/obs/views` lists them, and
`GET /v1/obs/views/{name}` returns one view's dimensions, measures, and
filters. `usage_report.py` uses `cost_hourly`, `user_daily`, `git_events`, and
`events`.

```bash
curl -s -X POST https://api.highflame.ai/v1/obs/query \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "view": "user_daily",
    "chart_type": "table",
    "dimensions": ["user_id"],
    "measures": ["event_count", "total_tokens"],
    "time_range": {"start": "2026-08-01T00:00:00Z", "end": "2026-08-28T00:00:00Z"},
    "order_by": [{"name": "total_tokens", "desc": true}]
  }'
```

---

## Notes

**Every export is scoped to one account and one project.** Your key carries
both. The server filters on them, so a key for project A never returns project
B's data. Both scripts decode the scope from the token and stamp it on the
output: `account_id` and `project_id` are the first two columns of the CSV and
the first two keys of every JSON record. Pass `--no-tenant-columns` to
`export_events.py` if you want the raw API shape.

If your org runs several projects, create one key per project and merge the
results yourself.

**Paging.** The events endpoint caps `limit` at 100. `export_events.py` pages
through automatically and stops when the server runs out. Use `--max` to cap
the export.

**A failed export will not overwrite a good one.** A long export can die on
page 30 of 40. With `-o`, the script writes to a temporary file beside the
target and renames it only after the last page lands, so a scheduled reader
never picks up a well-formed but truncated file. On failure the previous export
stays where it is and the exit code is 1. Check it in your cron wrapper.

**Rate limits and transient failures.** Both scripts retry a 429 or a 5xx three
times with a linear backoff, then give up with the server's message.

**What an export contains.** Events carry metadata, not prompt text: who, when,
which agent, which model, the decision, token counts, cost, latency, and which
detectors fired. Use the event detail endpoint if you need the payload for a
specific event.

**Scheduling.** Nothing here holds state, so a cron entry is enough:

```cron
0 6 * * 1 cd /path/to/usage-reporting && python usage_report.py --since 7d --format json -o /var/reports/highflame-$(date +\%F).json
```
