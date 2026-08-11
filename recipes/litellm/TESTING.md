# LiteLLM × Shield — test matrix

Status legend: ✅ validated against dev1 (2026-08-11, via litellm's real translation
layer where noted) · ⬜ not yet exercised · ❌ known gap, not implemented.

## 1. Content surfaces

| # | Surface | Direction | Hook (`mode:`) | Shield evaluation | Test cases | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | User prompt | request | `pre_call` | `process_prompt` / prompt | benign passes; injection detected | ✅ |
| 2 | System / developer prompt | request | `pre_call` (same `texts` scan) | `process_prompt` / prompt | injection planted in system text detected | ⬜ scanned mechanically (in `texts`), no adversarial case run |
| 3 | LLM response text | response | `post_call` | `process_prompt` / response | benign passes; policy-violating text blocked | ✅ |
| 4 | LLM response text — **streaming** | response | `post_call` (sampled rounds + end-of-stream flush) | same as #3 | verdict fires; redacted text re-emitted as synthetic deltas | ⬜ needs live proxy |
| 5 | LLM tool call (local/client-executed) | response | `post_call` | `call_tool` per proposed call | `rm -rf`, `curl \| sh` → `command_injection` signal fired (score 85) | ✅ |
| 6 | LLM tool call — **streaming** | response | end-of-stream block inspection | `call_tool` | assembled tool call blocked at stream end; client that waits for stream completion never executes | ⬜ needs live proxy |
| 7 | Local tool **result** (`role: "tool"` message) | next request | `pre_call` | `process_prompt` per text segment | planted secret in tool output scanned | ✅ via real `OpenAIChatCompletionsHandler` |
| 8 | MCP tool call (name + arguments) | request | `pre_mcp_call` | `call_tool` | exfil-shaped `send_email` args evaluated | ✅ synthetic dispatch payload |
| 9 | MCP tool result (`content`) | response | `post_mcp_call` | `process_prompt` / response | PII in result scanned | ✅ |
| 10 | MCP tool result (`structuredContent`) | response | `post_mcp_call` | same call as #9 (litellm includes it) | structured-only payload scanned/masked | ⬜ |
| 11 | Tool **definitions** (`tools=[...]` schemas/descriptions) | request | `pre_call` | `call_tool` with `ToolContext.description` (tool-poisoning analysis) | poisoned description → `Credential Leakage` + `Path Traversal` signals (100); hash-dedup across turns; changed definition (rug pull) re-scanned; MCP synthetic entry not double-scanned | ✅ |
| 12 | Images / multimodal input | request | — | — | — | ❌ out of scope (guardrail ignores `inputs["images"]`; text parts of multimodal messages ARE scanned) |

## 2. Decision outcomes (cross with any surface above)

| Decision | Expected proxy behavior | Status |
| --- | --- | --- |
| `allow` | traffic proceeds untouched | ✅ |
| `deny` | HTTP 400 with policy reason | ✅ mechanism; ⬜ end-to-end (dev1 canary tenant is permit-all / monitor — see §5) |
| `modify` (redaction) | Shield's `redacted_content` written back; litellm logs "mask" | ⬜ code path implemented; no tenant policy fired it |
| `step_up` / `defer` | treated as blocked (400) — proxy has no step-up UX | ⬜ |
| Shield unreachable / timeout / 5xx | **currently fails closed** (SDK error propagates → request rejected). Confirm this is the wanted default; consider a `fail_open` knob | ⬜ decision + test needed |

## 3. Session & scale behavior (coding agents)

| Case | Expected | Status |
| --- | --- | --- |
| Incremental scan, turn N+1 (unchanged history + 1 new msg) | only new segment scanned | ✅ |
| Edited earlier message (hash changes) | edited segment re-scanned | ⬜ |
| Blocked segment, client retries | re-checked (never marked scanned) | ⬜ |
| No session id on request | falls back to full scan (logged) | ⬜ |
| Historical `tool_calls` in resent conversation | **not** re-evaluated | ✅ |
| Redaction + `only_scan_new_messages` together | scan-only, write-back skipped (litellm contract) | ⬜ |
| Latency budget | measure Shield RTT added per hook point under agent-sized contexts | ⬜ |

## 4. Endpoint / wiring shapes

| Case | Why | Status |
| --- | --- | --- |
| `/chat/completions` (OpenAI shape) | primary path | ✅ translation-layer level |
| `/v1/messages` (Anthropic shape) | Claude Code & many agents speak this through LiteLLM | ⬜ (handler exists; needs proxy env with fastapi) |
| `/responses` (OpenAI Responses API) | litellm transforms `input` → messages | ⬜ |
| Live proxy e2e (`litellm --config` + guardrails YAML + MCP gateway) | validates YAML wiring, not just hook dispatch | ⬜ needs proxy extras + real provider key |
| Parallel tool calls in one response | loop coverage | ⬜ |
| Malformed tool arguments (non-JSON) | handled via `{"_raw": ...}` fallback | ⬜ unit case |
| `during_call` / `during_mcp_call` modes | parallel, non-blocking evaluation — observability-only posture | ⬜ |
| JWT refresh over long-lived proxy | SDK auto-refresh under sustained traffic | ⬜ |

## 5. Standing caveat — tenant policy config

Detection ≠ blocking: detectors fire regardless, but the Cedar decision comes from the
tenant's policies. The dev1 canary tenant resolves to "Baseline Permit All" with the
injection policy in monitor mode, so nothing visibly blocks there. Deny/redact rows
need a tenant with matching **enforce**-mode policies (injection on prompts, tool-risk
thresholds on `call_tool`, PII-redact on responses) authored in Studio first.
