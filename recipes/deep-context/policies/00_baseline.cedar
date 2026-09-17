// =============================================================================
// Baseline Permit
// =============================================================================
// Cedar is default-deny. Without at least one permit rule, every request is
// denied regardless of what the forbid rules below say — and the guard
// response looks identical to a policy working correctly, which makes this
// the single most common way a fresh project appears "broken".
//
// Load this FIRST in a new project. If the project already carries the
// platform default "Permit baseline" policy, skip this file.
//
// Category:  organization
// Namespace: Guardrails
// =============================================================================

@id("organization.permit-baseline")
@name("Permit baseline")
@description("Permits all Guardrails actions. Threat-specific forbid rules override it.")
@severity("low")
@tags("category:organization,posture:permit-default")
permit (
    principal,
    action,
    resource
);
