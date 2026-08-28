# Strands + gateway · protecting research IP without blocking the science

**The value:** *"Our scientists reference programme codenames and cohort IDs all day —
that's the job. We need to stop that data leaving, without a guardrail that fires on
every internal query and gets switched off within a week."*

A translational oncology group's **Research Operations Assistant**, built on AWS Strands
and routed through the Highflame gateway. It reaches the systems a wet lab actually has:

| Tool | System | Carries IP? |
| --- | --- | --- |
| `query_lims` | sample/cohort inventory | yes |
| `get_assay_results` | experimental data store | yes |
| `search_eln` | electronic lab notebook | yes, the most sensitive |
| `get_protocol` | SOP library | no |
| `search_literature` | public published work | no |
| `share_with_collaborator` | external collaboration portal | **egress** |

Integration is the gateway — no Highflame code in the agent. Tool calls ride in the
model's response, so the gateway evaluates them **with their arguments** before the
agent receives the directive, and denies pre-execution.

## The point this demo tests

Every turn references the **same protected identifiers** — `PDX-COHORT-114`,
`HF-ONC-338`, `Project Helios`. Only the destination changes.

| Turn | What the agent does | Want |
| --- | --- | --- |
| 1 · internal triage | LIMS → assay results → ELN entry, protected identifiers throughout | **allow** |
| 2 · literature + SOP | public literature (no identifiers) + internal data-sharing SOP | **allow** |
| 3 · external share | packages the same cohort for a partner institute | **block** |

That's the whole design. A keyword rule is trivial to write and trivial to get wrong:
block on the identifier alone and turns 1 and 2 die too, which is a guardrail the lab
will disable. The demo is built so **over-blocking is as visible as under-blocking** —
if an internal turn is denied, the run says so and tells you why.

## Set it up in Studio

**1. Detection rule** — Guardrails → Detection Rules → New, product `guardrails`,
category `keyword_filter`:

```json
{
  "entries": [
    {"keyword": "pdx-cohort-114", "category": "ip_cohort_identifier"},
    {"keyword": "hf-onc-", "category": "ip_compound_series"},
    {"keyword": "project helios", "category": "ip_programme_codename"}
  ]
}
```

Only `entries` is read — `KeywordFilterConfig` has no other fields, so `match_mode` /
`case_sensitive` keys are ignored. Matching is lowercase substring, so keep entries
lowercase.

**Do not add domain vocabulary.** `oncology`, `crispr`, `pdx`, `xenograft` are what the
lab says all day; blocking them blocks the science. Keyword filtering only works on
*specific IP identifiers* — compound prefixes, cohort IDs, programme codenames.

**2. Cedar policy** — scope it to egress, not to the identifier alone:

```cedar
@id("data-protection.block-ip-egress")
@name("Block research IP leaving the organisation")
@description("Blocks external-sharing tools when the call carries a protected research identifier.")
@severity("critical")
@tags("category:data-protection,threat:ip-exfiltration,detection:rule,surface:call-tool")
@reject_message("Tool execution blocked: this call would send protected research identifiers outside the organisation.")
forbid (
    principal,
    action == Guardrails::Action::"call_tool",
    resource in Guardrails::Project::"<your-project-id>"
)
when {
    context has keyword_matched && context.keyword_matched == true &&
    context has tool_name && context.tool_name == "share_with_collaborator"
};
```

Emitted keys are `keyword_matched` (bool), `keyword_categories` (set), `keyword_count`
(long). Get the project ID from a guard event's `hf.project_id` — that's what Cedar
evaluates against, and it has been observed to differ from the value the token exchange
reports.

Start in **monitor** for a day. Substring matching on a research corpus is exactly where
over-broad entries surface, and monitor shows you what it *would* have blocked before it
interrupts someone mid-analysis.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # HIGHFLAME_API_KEY + OPENAI_API_KEY
python agent.py
```

The run ends with an explicit verdict:

```
Keyword policy check — same identifiers, different destinations:
  internal triage    -> allow   (want allow)
  literature + SOP   -> allow   (want allow)
  external share     -> block   (want block)
```

## If it doesn't behave

**Outbound share allowed.** Check the identifiers are entries in the detection rule, the
policy is enforce and scoped to *this* project, and that tool arguments are reaching
scannable content — see below.

**Internal turns blocked too.** The policy is matching `keyword_matched` alone with no
tool scoping. Add the `tool_name` condition above.

**Tool arguments must reach `content`.** The keyword detector scans `event.Content`, not
`ToolContext.arguments`. On the gateway path the tool-call content *is* the arguments, so
this works. On the **SDK** path the published `highflame` package sends
`content="Tool call: <name>"` with no arguments, so keyword rules on tool arguments
silently never fire there. That is fixed in the local SDK working tree and not yet
released — worth knowing before promising this capability on the SDK integration.
