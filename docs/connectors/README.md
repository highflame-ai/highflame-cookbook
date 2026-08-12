# Registry connectors

Configure your identity and cloud providers so Highflame can discover agents and
adopt them into the registry.

In [Highflame Studio](https://studio.highflame.ai): **Registry → Connectors → Add
connector**, then pick the provider you run. Each guide below is the work you do
*in that provider* before (or while) completing the Studio form.

| Provider | Guide | What you set up |
| --- | --- | --- |
| **Microsoft Entra** | [entra.md](entra.md) | App registration, API permissions, client credentials |
| **AWS** | [aws.md](aws.md) | IAM role / access for agent discovery |
| **GCP** | [gcp.md](gcp.md) | Service account and APIs for agent discovery |
| **Okta** | [okta.md](okta.md) | OIDC / API app for agent discovery |

After the connector is healthy, continue with
[Agent governance](../../recipes/agent-governance/) — discover, adopt, assign an
owner, and attach a guardrail.

---

## Screenshots

Product screenshots live in [`images/`](images/). Name files by provider and step,
for example:

```text
images/entra-01-app-registration.png
images/okta-02-api-scopes.png
```
