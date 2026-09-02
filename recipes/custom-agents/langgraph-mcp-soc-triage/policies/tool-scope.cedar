// Per-agent tool scoping — the runtime half of the authorization beat.
//
// Issuance-time scoping already happened before Cedar ever runs: each worker's
// token was minted with attenuated scopes (tools:logs:read for the collector,
// tools:intel:read for the analyst), and the token-exchange triple intersection
// (requested ∩ delegator ∩ allowed) refuses to widen them. This policy is the
// second, independent layer: even a token that somehow names a tool is checked
// against the identity's allowed tool list at call time.
//
// The demo's deny beat lands here: the Threat Analyst calling block_ip gets
// 403 with this policy's id as the determining policy.

forbid (
  principal is Guardrails::Agent,
  action == Guardrails::Action::"tool_call",
  resource
) unless {
  resource.name in context.nhi_allowed_tools
};
