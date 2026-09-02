#!/usr/bin/env python3
"""A multi-agent LangGraph SOC that triages logs for suspicious traffic — with
per-agent identity, two delegation paths, layered authorization, and a CIBA
step-up on the one destructive action.

Four agents on one LangGraph StateGraph:

  soc-supervisor  routes the case; holds the RFC 8693 token exchanged over the
                  analyst's login (act.sub = the human)
  log-collector   reads flow/DNS/auth logs via the fronted soc-logs MCP server
                  (api_key grant, created_by=supervisor, tools:logs:read only)
  threat-analyst  scores the traffic via the fronted threat-intel MCP server
                  (tools:intel:read only) — and also calls the UNREGISTERED
                  geoip-community server directly, which is the shadow-MCP beat
  responder       executes containment (block_ip) — RFC 8693 with actor_token,
                  because write authority should carry a cryptographic chain

One triage run exercises all three AARM disposition classes:

  proceeded   allow (log queries) and modify (auth log comes back with employee
              emails REDACTED at HTTP 200 — redaction is an allow-class outcome)
  blocked     the threat-analyst oversteps twice: a scope-widening token
              request refused at ISSUANCE, then a direct block_ip refused at
              RUNTIME by Cedar (403 + determining policy id)
  suspended   the responder's block_ip matches @step_up_required("soc_lead"):
              Shield answers `decision: step_up`, the approver sees the
              binding_message in Studio's approval pane, the SDK polls the
              CIBA grant, and the retry proceeds on the upgraded token.
              Timeout or an explicit deny stays fail-closed.

Needs HIGHFLAME_API_KEY + OPENAI_API_KEY (see .env.example). The Studio
click-path — policies, MCP registry entries, the soc_lead role — is in the
README; without the step-up policy the block lands without approval and the
run warns.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Annotated, TypedDict

try:
    from dotenv import load_dotenv

    # override=True: the recipe's .env is authoritative. A HIGHFLAME_API_KEY
    # exported by the shell profile otherwise silently wins over the .env, and
    # a key from one environment against another's auth host fails as
    # "invalid api key" — which reads like a bad key, not a mixed pair.
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:  # dotenv is optional
    pass

from highflame import APIConnectionError, BlockedError, Highflame
from highflame.integrations.langgraph import HighflameMiddleware
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from identities import AgentIdentity, IdentityBroker, bootstrap
from stepup import StepUpChallenge, await_step_up

RUN_ID = uuid.uuid4().hex[:8]
DEMO_PACE = float(os.environ.get("DEMO_PACE", "0.35"))
HERE = Path(__file__).parent

# The seeded alert this run triages. Matches the beacon in mcp_servers/soc_logs.py.
ALERT = {
    "id": "alert-7031",
    "summary": "Periodic egress from ws-114.corp.example to a rare external host",
    "host": "ws-114.corp.example",
    "indicator": "203.0.113.7",
}


def _session_id(agent_name: str) -> str:
    # One Observatory session per agent per run, so the delegation story reads
    # as four principals working one case — not one blob of traffic.
    return f"{ALERT['id']}/{agent_name} ({RUN_ID})"


def _pace() -> None:
    if DEMO_PACE > 0:
        time.sleep(DEMO_PACE)


def _client_for(identity: AgentIdentity) -> Highflame:
    """A Highflame client bound to ONE agent's identity token."""
    kwargs = {"api_key": identity.token, "max_retries": 0}
    if os.environ.get("HIGHFLAME_BASE_URL"):
        kwargs["base_url"] = os.environ["HIGHFLAME_BASE_URL"]
    if os.environ.get("HIGHFLAME_TOKEN_URL"):
        kwargs["token_url"] = os.environ["HIGHFLAME_TOKEN_URL"]
    return Highflame(**kwargs)


# ---------------------------------------------------------------------------
# MCP wiring — three fronted servers + one deliberate shadow server
# ---------------------------------------------------------------------------

def _mcp_client(*server_names: str) -> MultiServerMCPClient:
    servers = {
        name: {
            "transport": "stdio",
            "command": sys.executable,
            "args": [str(HERE / "mcp_servers" / f"{name}.py")],
        }
        for name in server_names
    }
    return MultiServerMCPClient(servers)


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class TriageState(TypedDict):
    phase: str
    case_file: Annotated[list[str], lambda a, b: a + b]  # append-only case notes
    verdict: str          # "" until the analyst scores the traffic
    outcomes: Annotated[dict, lambda a, b: {**a, **b}]   # beat -> result


# ---------------------------------------------------------------------------
# Worker agents (LLM-driven, middleware-guarded)
# ---------------------------------------------------------------------------

COLLECTOR_PROMPT = (
    "You are the log-collection agent of a SOC triage team. For the case you are "
    "given: query egress flows for the suspect host, its DNS resolutions, and its "
    "authentication events. Summarize what you found as terse case notes — one "
    "line per finding, no speculation. Flag anything with unusually regular "
    "timing (low inter-arrival jitter)."
)

ANALYST_PROMPT = (
    "You are the threat-analysis agent of a SOC triage team. You receive case "
    "notes about a suspect host. Check the reputation and ASN of every external "
    "IP in the notes. Then give a verdict line exactly in this form:\n"
    "verdict: <benign|suspicious|confirmed-c2> confidence: <0..1> "
    "indicator: <ip>\nfollowed by two sentences of reasoning grounded in the "
    "tool results."
)


async def _run_worker(name: str, identity: AgentIdentity, system_prompt: str,
                      tools: list, task: str) -> tuple[str, str]:
    """Run one guarded worker agent; return (outcome, final_text)."""
    client = _client_for(identity)
    middleware = HighflameMiddleware(client, mode="enforce")
    model = ChatOpenAI(
        model=os.environ.get("DEMO_MODEL", "gpt-5.4-mini"),
        model_kwargs={"parallel_tool_calls": False},  # ordered guard events
    )
    agent = create_agent(model=model, tools=tools,
                         system_prompt=system_prompt, middleware=[middleware])
    try:
        result = await agent.ainvoke(
            {"messages": [HumanMessage(task)]},
            config={"configurable": {"thread_id": _session_id(name)}},
        )
    except BlockedError as exc:
        return "blocked", exc.response.policy_reason or exc.response.decision
    except APIConnectionError:
        return "error", "Highflame unreachable — set HIGHFLAME_BASE_URL / check network"
    return "ok", str(result["messages"][-1].content)


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def build_graph(cast: dict[str, AgentIdentity], broker: IdentityBroker):
    async def collect(state: TriageState) -> dict:
        print(f"[collect] log-collector on {ALERT['host']} "
              f"({cast['log-collector'].wimse_uri or 'bootstrap identity'})")
        async with _mcp_client("soc_logs") as mcp:
            tools = mcp.get_tools()
            outcome, notes = await _run_worker(
                "log-collector", cast["log-collector"], COLLECTOR_PROMPT, tools,
                f"Case {ALERT['id']}: {ALERT['summary']}. Suspect host: {ALERT['host']}. "
                "Collect flows, DNS, and auth events for it.",
            )
        _pace()
        # The auth-events result is where the modify beat lands: employee emails
        # come back redacted at HTTP 200 when the PII modify-mode policy is on.
        redacted = "[REDACTED" in notes or "█" in notes
        print(f"[collect] {outcome}; PII redaction visible in notes: {redacted}\n")
        return {
            "phase": "collected",
            "case_file": [notes],
            "outcomes": {"collect": outcome, "modify_redaction": str(redacted)},
        }

    async def enrich(state: TriageState) -> dict:
        print(f"[enrich] threat-analyst scoring the indicators "
              f"({cast['threat-analyst'].wimse_uri or 'bootstrap identity'})")
        # The shadow beat: geoip-community is mounted alongside the fronted
        # threat-intel server but is NOT in Studio's MCP registry. Its calls
        # succeed and leave no governed trace — that gap is what the MCP
        # coverage view exists to show.
        async with _mcp_client("threat_intel", "geoip_community") as mcp:
            tools = mcp.get_tools()
            outcome, analysis = await _run_worker(
                "threat-analyst", cast["threat-analyst"], ANALYST_PROMPT, tools,
                "Case notes so far:\n" + "\n\n".join(state["case_file"]),
            )
        _pace()
        verdict = "confirmed-c2" if "confirmed-c2" in analysis else (
            "suspicious" if "suspicious" in analysis else "benign")
        print(f"[enrich] {outcome}; verdict: {verdict}\n")
        return {"phase": "enriched", "case_file": [analysis],
                "verdict": verdict, "outcomes": {"enrich": outcome}}

    async def overreach(state: TriageState) -> dict:
        """The deny beats — the analyst tries to contain the threat itself.

        Scripted rather than model-driven: a demo must show the refusal every
        run, not only when the model happens to misbehave.
        """
        analyst = cast["threat-analyst"]
        print("[overreach] threat-analyst attempts containment it is not scoped for")

        # Layer 1 — issuance. Ask AuthN to widen the analyst's scopes to the
        # firewall. The token-exchange triple intersection refuses to widen.
        refused, detail = broker.attempt_scope_widening(analyst)
        print(f"  issuance layer: {'REFUSED' if refused else 'NOT REFUSED'} — {detail}")

        # Layer 2 — runtime. Call block_ip with the analyst's own token anyway.
        # Cedar's tool-scope policy answers deny (403 + determining policy id).
        runtime = "skipped"
        try:
            resp = _client_for(analyst).guard.evaluate_tool_call(
                "block_ip",
                {"ip": ALERT["indicator"], "reason": "analyst overreach (demo beat)"},
                session_id=_session_id("threat-analyst"),
            )
            runtime = resp.decision
            pol = (resp.determining_policies or [None])[0]
            print(f"  runtime layer: decision={resp.decision}"
                  + (f" (policy: {getattr(pol, 'id', pol)})" if pol else ""))
        except BlockedError as exc:
            runtime = "deny"
            print(f"  runtime layer: DENIED — {exc.response.policy_reason or '403'}")
        except APIConnectionError:
            print("  runtime layer: Highflame unreachable — beat skipped")
        _pace()
        print()
        return {"phase": "overreach-done",
                "outcomes": {"deny_issuance": "refused" if refused else "not-refused",
                             "deny_runtime": runtime}}

    async def contain(state: TriageState) -> dict:
        """The step-up beat — the responder blocks the C2 endpoint, gated on CIBA."""
        responder = cast["responder"]
        print(f"[contain] responder requests block_ip({ALERT['indicator']}) "
              f"({responder.wimse_uri or 'bootstrap identity'})")
        client = _client_for(responder)
        args = {
            "ip": ALERT["indicator"],
            "reason": f"C2 beaconing from {ALERT['host']}, verdict {state['verdict']} "
                      f"(case {ALERT['id']})",
        }
        try:
            resp = client.guard.evaluate_tool_call(
                "block_ip", args, session_id=_session_id("responder"))
        except BlockedError as exc:
            print(f"[contain] DENIED outright: {exc.response.policy_reason}\n")
            return {"phase": "done", "outcomes": {"contain": "deny"}}
        except APIConnectionError:
            print("[contain] Highflame unreachable\n")
            return {"phase": "done", "outcomes": {"contain": "error"}}

        if resp.decision == "step_up":
            # Shield already POSTed AuthN's bc-authorize; the challenge fields
            # ride in the response context (auth_req_id, interval, expires_in,
            # binding_message). Poll the CIBA grant until the soc_lead resolves.
            ctx = {**(resp.projected_context or {}), **(resp.context or {})}
            challenge = StepUpChallenge.from_response(ctx)
            result = await_step_up(challenge)
            if result.outcome != "approved":
                print(f"[contain] containment refused by operator ({result.outcome})\n")
                return {"phase": "done", "outcomes": {"contain": f"step_up:{result.outcome}"}}
            retry_ident = AgentIdentity(name="responder", token=result.access_token,
                                        scopes=responder.scopes)
            resp = _client_for(retry_ident).guard.evaluate_tool_call(
                "block_ip", args, session_id=_session_id("responder"))
            print(f"[contain] retry on upgraded token: decision={resp.decision}")
        elif resp.decision == "allow":
            print("[contain] WARN: block_ip was allowed WITHOUT approval — is the "
                  "@step_up_required('soc_lead') policy active for this tenant?")

        if resp.decision not in ("allow", "modify"):
            print(f"[contain] not executed (decision={resp.decision})\n")
            return {"phase": "done", "outcomes": {"contain": resp.decision}}

        # Decision proceeded — actually apply the rule on the MCP server.
        async with _mcp_client("edge_firewall") as mcp:
            tools = {t.name: t for t in mcp.get_tools()}
            applied = await tools["block_ip"].ainvoke(args)
            rules = await tools["list_rules"].ainvoke({})
        print(f"[contain] applied: {applied}")
        print(f"[contain] firewall rules this run: {rules}\n")
        return {"phase": "done", "outcomes": {"contain": "step_up:approved"}}

    g = StateGraph(TriageState)
    g.add_node("collect", collect)
    g.add_node("enrich", enrich)
    g.add_node("overreach", overreach)
    g.add_node("contain", contain)
    g.set_entry_point("collect")
    g.add_edge("collect", "enrich")
    # The supervisor's routing decision: containment only on a confirmed
    # verdict; a benign case ends the run after the deny beats.
    g.add_edge("enrich", "overreach")
    g.add_conditional_edges(
        "overreach",
        lambda s: "contain" if s["verdict"] in ("confirmed-c2", "suspicious") else END,
        {"contain": "contain", END: END},
    )
    g.add_edge("contain", END)
    return g.compile()


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

async def main() -> int:
    for var in ("HIGHFLAME_API_KEY", "OPENAI_API_KEY"):
        if not os.environ.get(var):
            print(f"SKIP: {var} not set (see .env.example).")
            return 2

    print(f"[case] {ALERT['id']}: {ALERT['summary']}\n")
    broker = IdentityBroker()
    cast = bootstrap()

    graph = build_graph(cast, broker)
    final = await graph.ainvoke(
        {"phase": "new", "case_file": [], "verdict": "", "outcomes": {}})

    print("[case] run complete — beat outcomes:")
    for beat, result in final["outcomes"].items():
        print(f"  {beat}: {result}")
    print("\nOpen Observatory: four sessions (one per agent), the deny with its "
          "determining policy, the approval receipt on the responder's session, "
          "and geoip-community as the shadow row in MCP coverage.")
    return 0 if "error" not in final["outcomes"].values() else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
