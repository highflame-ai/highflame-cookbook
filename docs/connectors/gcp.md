# GCP — connector setup

Configure Google Cloud so Highflame can connect under **Registry → Connectors**.

## Before you start

- Access to the [Google Cloud Console](https://console.cloud.google.com/) with
  permission to create service accounts and enable APIs.
- A GCP project that hosts (or can list) the agents you want to discover.
- Your Highflame tenant open in Studio on **Registry → Connectors → Add → GCP**.

## 1. Enable required APIs

1. **APIs & Services** → **Library**.
2. Enable the APIs Highflame lists in Studio for this connector (e.g. Vertex AI /
   Agent Engine / IAM-related APIs for your setup).

![Enable APIs](images/gcp-01-enable-apis.png)

<!-- Replace the image above with a real GCP Console screenshot. -->

## 2. Create a service account

1. **IAM & Admin** → **Service accounts** → **Create service account**.
2. Name it (e.g. `highflame-connector`).
3. Grant the least-privilege roles Highflame lists in Studio.
4. Finish creation.

![Service account](images/gcp-02-service-account.png)

## 3. Create a key

1. Open the service account → **Keys** → **Add key** → **Create new key**.
2. Type **JSON** → Create.
3. Store the downloaded JSON securely; you will upload or paste fields into Studio.

![Service account key](images/gcp-03-service-account-key.png)

## 4. Note project identifiers

From the project dashboard / settings, copy:

- **Project ID**
- **Project number** (if Studio asks for it)

![Project ID](images/gcp-04-project-id.png)

## 5. Complete the connector in Studio

In Studio → **Registry → Connectors**, provide:

| Studio field | GCP value |
| --- | --- |
| Project ID | GCP project ID |
| Service account email | `…@….iam.gserviceaccount.com` |
| Credentials | Service account JSON (or fields Studio requests) |
| Region / location | Where agents run (if prompted) |

Save and wait for the connector status to become healthy.

## Verify

- Connector shows **Connected** / healthy in Studio.
- Discovered agents appear under the registry (see
  [Agent governance](../../recipes/agent-governance/)).
