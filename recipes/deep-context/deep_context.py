"""Shared helpers for the deep-context recipe.

Everything here is a thin wrapper over the Highflame SDK. The point of the
wrapper is to pull the four numbers that matter out of the guard response and
put them side by side, because the whole story of this recipe is the gap
between two of them:

    injection_pulse_score         what a single-turn filter sees
    injection_deep_context_score  what a model with conversation memory sees

Those live in ``GuardResponse.projected_context``, which Shield only populates
when the request asks for ``explain=True``. Every call below asks for it.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional; env vars may already be set.
    pass


class RecipeError(RuntimeError):
    """Configuration or connectivity problem the user needs to fix."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Resolved environment for the recipe."""

    api_key: str
    base_url: str
    token_url: str
    observatory_url: str
    studio_url: str
    agent_label: str
    operator: str

    @property
    def ready(self) -> bool:
        return bool(self.api_key)

    @property
    def can_query_observatory(self) -> bool:
        return bool(self.api_key and self.observatory_url)


def load_config() -> Config:
    """Read the recipe's environment. Never raises — check ``.ready``."""
    base_url = os.getenv("HIGHFLAME_BASE_URL", "https://api.highflame.ai").rstrip("/")
    return Config(
        api_key=os.getenv("HIGHFLAME_API_KEY", "").strip(),
        base_url=base_url,
        token_url=os.getenv(
            "HIGHFLAME_TOKEN_URL", "https://auth.highflame.ai/oauth2/token"
        ).rstrip("/"),
        observatory_url=os.getenv("HIGHFLAME_OBSERVATORY_URL", "").rstrip("/"),
        studio_url=os.getenv("HIGHFLAME_STUDIO_URL", "https://studio.highflame.ai").rstrip("/"),
        agent_label=os.getenv("HIGHFLAME_AGENT_LABEL", "research-agent"),
        operator=os.getenv("HIGHFLAME_OPERATOR", "unset@example.com"),
    )


def connect(cfg: Config | None = None):
    """Build an authenticated SDK client."""
    cfg = cfg or load_config()
    if not cfg.ready:
        raise RecipeError(
            "HIGHFLAME_API_KEY is not set. Copy .env.example to .env and add a key "
            "from Studio → Settings → API Keys."
        )

    from highflame import Highflame

    return Highflame(api_key=cfg.api_key, base_url=cfg.base_url, token_url=cfg.token_url)


def new_session_id(prefix: str = "deepctx") -> str:
    """A fresh session id. Session state is keyed on this, so re-running the
    notebook with a stale id would resume the previous run's hidden state."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# One evaluated turn
# ---------------------------------------------------------------------------


def _as_int(ctx: dict[str, Any], key: str) -> int:
    """Projected scores are Cedar Longs, but be tolerant of float/str/None."""
    value = ctx.get(key)
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


@dataclass
class TurnResult:
    """One guard evaluation, flattened to the fields this recipe talks about."""

    index: int
    text: str
    decision: str
    actual_decision: str
    effective_mode: str
    policy_reason: str

    # The two views of the same turn. The gap between them is the recipe.
    injection_pulse: int
    injection_deep: int
    jailbreak_pulse: int
    jailbreak_deep: int

    # Proof the threaded state was actually used.
    multi_turn: bool
    conversation_turn: int

    # Session-accumulated history.
    cumulative_risk: int
    threat_turns: int
    session_max_injection: int
    session_max_jailbreak: int

    determining_policies: list[str] = field(default_factory=list)
    reject_messages: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    latency_ms: int = 0
    request_id: str = ""
    raw: Any = None

    @property
    def blocked(self) -> bool:
        """True when the policy set said no.

        Reads ``actual_decision`` when present, not ``decision``: a policy in
        monitor mode returns decision="allow" with actual_decision="deny", and
        reading only ``decision`` is the standard way to conclude "nothing
        fired" when in fact everything fired and nothing was enforced.
        """
        return (self.actual_decision or self.decision) == "deny"

    @property
    def enforced(self) -> bool:
        """True when the block was actually applied rather than just logged."""
        return self.decision == "deny"

    @property
    def divergence(self) -> int:
        """How much more the conversation-aware model saw than the single-turn
        one. This is the number that cannot exist without session state."""
        return max(
            self.injection_deep - self.injection_pulse,
            self.jailbreak_deep - self.jailbreak_pulse,
        )


def guard_prompt(client, text: str, *, session_id: str | None, index: int = 0) -> TurnResult:
    """Evaluate one conversational turn.

    Pass ``session_id=None`` to score the turn in isolation — that is the
    stateless control, and what a filter with no conversation memory can see.
    """
    resp = client.guard.evaluate(
        content=text,
        content_type="prompt",
        action="process_prompt",
        session_id=session_id or "",
        explain=True,
    )
    return _to_turn(resp, index=index, text=text)


def guard_tool(
    client,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    session_id: str | None,
    index: int = 0,
) -> TurnResult:
    """Evaluate a tool call on the same session as the conversation.

    Threading the tool call onto the conversation's session_id is the whole
    mechanism behind policy 02: the tool call is judged against what the
    conversation has been doing, not just against its own arguments.
    """
    from highflame._types_gen import ToolContext

    resp = client.guard.evaluate(
        content=f"Tool call: {tool_name}",
        content_type="tool_call",
        action="call_tool",
        session_id=session_id or "",
        tool=ToolContext(name=tool_name, is_builtin=False, arguments=arguments or {}),
        explain=True,
    )
    return _to_turn(resp, index=index, text=f"{tool_name}({arguments or {}})")


def _to_turn(resp, *, index: int, text: str) -> TurnResult:
    ctx = resp.projected_context or {}
    return TurnResult(
        index=index,
        text=text,
        decision=resp.decision,
        actual_decision=resp.actual_decision or "",
        effective_mode=resp.effective_mode or "",
        policy_reason=resp.policy_reason or "",
        injection_pulse=_as_int(ctx, "injection_pulse_score"),
        injection_deep=_as_int(ctx, "injection_deep_context_score"),
        jailbreak_pulse=_as_int(ctx, "jailbreak_pulse_score"),
        jailbreak_deep=_as_int(ctx, "jailbreak_deep_context_score"),
        multi_turn=bool(ctx.get("multi_turn_detection", False)),
        conversation_turn=_as_int(ctx, "conversation_turn"),
        cumulative_risk=_as_int(ctx, "session_cumulative_risk_score"),
        threat_turns=_as_int(ctx, "session_threat_turns"),
        session_max_injection=_as_int(ctx, "session_max_injection_score"),
        session_max_jailbreak=_as_int(ctx, "session_max_jailbreak_score"),
        # The rule that fired is `rule_id` — the `@id(...)` you wrote. There is
        # no `.id` attribute on this object; reading one silently yields an
        # empty list and makes a firing policy look like nothing fired.
        determining_policies=[
            p.rule_id for p in (resp.determining_policies or []) if getattr(p, "rule_id", None)
        ],
        # `policy_reason` on the envelope is a detector-derived summary
        # ("deepcontext scored 97"). The @reject_message you authored — the
        # text meant for the end user — rides in the rule's annotations.
        reject_messages=[
            msg
            for p in (resp.determining_policies or [])
            if (msg := (getattr(p, "annotations", None) or {}).get("reject_message"))
        ],
        signals=[f"{s.vulnerability_id}:{s.score}" for s in (resp.signals or [])],
        latency_ms=resp.latency_ms,
        request_id=resp.request_id,
        raw=resp,
    )


# ---------------------------------------------------------------------------
# Running a whole conversation, both ways
# ---------------------------------------------------------------------------


def run_threaded(client, turns: list[str], session_id: str) -> list[TurnResult]:
    """Every turn on ONE session id, so DeepContext carries hidden state
    forward and Shield accumulates session history. This is a real
    conversation."""
    return [
        guard_prompt(client, t, session_id=session_id, index=i)
        for i, t in enumerate(turns, start=1)
    ]


def run_stateless(client, turns: list[str]) -> list[TurnResult]:
    """Every turn scored in isolation — a fresh session per turn.

    This is the control, and it is what a stateless content filter (Bedrock
    Guardrails, a regex tier, a single-turn classifier) is structurally
    limited to. Same text, same detectors, no memory.
    """
    return [
        guard_prompt(client, t, session_id=new_session_id("isolated"), index=i)
        for i, t in enumerate(turns, start=1)
    ]


# ---------------------------------------------------------------------------
# Observatory — the attribution view
# ---------------------------------------------------------------------------


def _bearer(cfg: Config) -> str:
    """Observatory takes the same RS256 JWT Shield does, so mint one the same
    way the SDK does rather than re-implementing the exchange."""
    if not cfg.api_key.startswith(("zid_sk", "hf_sk", "hfa_")):
        return cfg.api_key  # already a JWT

    resp = httpx.post(
        cfg.token_url,
        json={"grant_type": "api_key", "api_key": cfg.api_key},
        timeout=20.0,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RecipeError(f"token exchange at {cfg.token_url} returned no access_token")
    return token


def session_events(cfg: Config, session_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
    """Every recorded step of one session, in order.

    GET /v1/obs/sessions/{session_id}/events — this is the API behind the
    session timeline in Studio, and the answer to "show us what the agent
    actually did."
    """
    if not cfg.can_query_observatory:
        raise RecipeError(
            "Set HIGHFLAME_OBSERVATORY_URL to query the session timeline directly. "
            "Without it, open the session in Studio instead (see session_url())."
        )

    resp = httpx.get(
        f"{cfg.observatory_url}/v1/obs/sessions/{session_id}/events",
        params={"limit": limit},
        headers={"Authorization": f"Bearer {_bearer(cfg)}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("events", payload if isinstance(payload, list) else [])


def attribution(event: dict[str, Any]) -> dict[str, str]:
    """Pull the dual-attribution pair out of an Observatory event.

    ``user_id`` is the accountable human; ``labels.agent_id`` is the agent
    that acted. An event with one and not the other is the gap policy 03
    exists to close.
    """
    labels = event.get("labels") or {}
    return {
        "user": event.get("user_id") or event.get("user_name") or "—",
        "agent": labels.get("agent_id") or event.get("agent_id") or "—",
        "trust": labels.get("agent_trust_level", "—"),
        "action": event.get("event_type", "—"),
        "tool": event.get("tool_name") or labels.get("mcp_server") or "—",
        "decision": event.get("decision", "—"),
        "severity": event.get("highest_severity") or "—",
        "trace": event.get("trace_id", "—"),
    }


def session_url(cfg: Config, session_id: str) -> str:
    """Where a human goes to see this session in Studio."""
    return f"{cfg.studio_url}/observatory/sessions/{session_id}"
