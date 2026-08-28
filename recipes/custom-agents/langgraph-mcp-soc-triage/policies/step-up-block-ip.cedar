// The step-up gate — the CIBA beat.
//
// `block_ip` is permitted for the responder, but the @step_up_required
// annotation makes Shield return `decision: step_up` instead of allow:
// Shield (the CIBA client) POSTs AuthN's /oauth2/bc-authorize with a
// binding_message + RFC 9396 authorization_details, and the agent gets an
// RFC 9470 challenge (401, insufficient_user_authentication, auth_req_id).
// Every user in the soc_lead role sees the typed prompt in Studio's approval
// pane; first approver wins. On approval the SDK's poll returns a token
// carrying the granted authorization_details claim, the call is retried, and
// this same policy evaluates to allow.
//
// Timeout is fail-closed: if nobody resolves within the CIBA expires_in,
// the action is denied.
//
// The annotation registry (Wave A, highflame-policy#119) validates
// @step_up_required at deploy time — "soc_lead" must resolve to a role.

@step_up_required("soc_lead")
permit (
  principal is Guardrails::Agent,
  action == Guardrails::Action::"tool_call",
  resource == Guardrails::Tool::"block_ip"
);
