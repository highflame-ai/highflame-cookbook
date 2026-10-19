# Self-managed recipes

These recipes need a **customer-managed Highflame deployment**. They do not run against
Highflame's hosted service yet.

They use features that a customer-managed deployment turns on:

- **Person federation.** Highflame links a person who signed in with your identity provider to a
  member of your organization, by a verified email on one of your claimed domains. That needs
  domain join, which a customer-managed deployment enables in Admin
  (`HIGHFLAME_DEPLOYMENT_MODEL=self_managed`, `HIGHFLAME_TENANCY_DOMAIN_JOIN_ENABLED=true`).
- **Roles your operator assigns.** A platform operator (Admin's `tenancy.bootstrap_super_admins`)
  claims your email domains. Your organization's owner trusts and verifies your identity provider.

| Recipe | What it shows | Format |
| --- | --- | --- |
| [User delegation](user-delegation/) | An agent acts for a person signed in with Okta: their ID token, or an Okta ID-JAG, for a Highflame token. The full example is a Strands agent on Amazon Bedrock AgentCore, behind the Highflame LLM and MCP gateways, with gateway policies for one person. | Notebook and Python scripts |
