# Okta — connector setup

Configure Okta so Highflame can connect under **Registry → Connectors**.

## Before you start

- Access to the [Okta Admin Console](https://login.okta.com/) with permission to
  create apps and API tokens / OAuth clients.
- Your Highflame tenant open in Studio on **Registry → Connectors → Add → Okta**.
- Your Okta org domain (e.g. `https://your-org.okta.com`).

## 1. Create an API / OIDC application

1. Admin Console → **Applications** → **Applications** → **Create App Integration**.
2. Choose the app type Studio documents for this connector (typically **API Services**
   or **OIDC - Web** depending on the Highflame form).
3. Name it (e.g. `Highflame Connector`) and save.

![Create app](images/okta-01-create-app.png)

<!-- Replace the image above with a real Okta Admin screenshot. -->

## 2. Configure client credentials

1. Open the app → **General** / **Client Credentials**.
2. Copy **Client ID**.
3. Generate or reveal **Client secret** and copy it once.

![Client credentials](images/okta-02-client-credentials.png)

## 3. Grant scopes / API access

1. Assign the scopes and Okta API access Highflame lists in Studio (directory read /
   agent-related APIs as applicable).
2. If using an admin API token instead of (or in addition to) OAuth, create one under
   **Security** → **API** → **Tokens** with least privilege.

![Scopes](images/okta-03-scopes.png)

## 4. Complete the connector in Studio

In Studio → **Registry → Connectors**, paste:

| Studio field | Okta value |
| --- | --- |
| Okta domain | `https://your-org.okta.com` |
| Client ID | From the app |
| Client secret | From the app |
| API token | Admin token, if Studio requires it |

Save and wait for the connector status to become healthy.

## Verify

- Connector shows **Connected** / healthy in Studio.
- Discovered agents appear under the registry (see
  [Agent governance](../../recipes/agent-governance/)).
