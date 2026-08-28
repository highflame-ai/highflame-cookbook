// Delegation-chain governance.
//
// AuthN enforces a per-project maximum delegation depth (default 3) at token
// exchange. This policy is the belt to that suspenders: Cedar sees the chain
// on every guarded call (context.delegation_depth, context.delegated_by,
// context.delegation_chain) and refuses anything deeper than the two hops the
// demo architecture actually uses (analyst -> supervisor -> worker).

forbid (
  principal,
  action,
  resource
) when {
  context.delegation_depth > 2
};

// Only the supervisor may delegate. Workers are leaves: a worker minting
// further sub-identities is outside the demo's design and is refused.
forbid (
  principal is Guardrails::Agent,
  action == Guardrails::Action::"delegate",
  resource
) unless {
  context.agent_type == "orchestrator"
};
