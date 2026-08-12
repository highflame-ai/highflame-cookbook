# AWS — connector setup

Configure AWS so Highflame can connect under **Registry → Connectors**.

## Before you start

- Access to the [AWS Management Console](https://console.aws.amazon.com/) with
  permission to create IAM roles or users and attach policies.
- Your Highflame tenant open in Studio on **Registry → Connectors → Add → AWS**.
- Prefer an **IAM role** Highflame can assume (recommended) over long-lived access
  keys when Studio supports it.

## 1. Create an IAM policy for discovery

1. IAM → **Policies** → **Create policy**.
2. Attach the least-privilege actions Highflame lists in Studio for this connector
   (agent / Bedrock / related discovery APIs for your account).
3. Name it (e.g. `HighflameConnectorDiscovery`) and create the policy.

![IAM policy](images/aws-01-iam-policy.png)

<!-- Replace the image above with a real AWS Console screenshot. -->

## 2. Create the IAM principal

### Option A — Role (preferred)

1. IAM → **Roles** → **Create role**.
2. Choose the trust type Studio documents (external Id / account that Highflame uses).
3. Attach `HighflameConnectorDiscovery`.
4. Name the role (e.g. `HighflameConnector`) and create it.
5. Copy the **Role ARN**.

![IAM role](images/aws-02-iam-role.png)

### Option B — User + access keys

1. IAM → **Users** → **Create user**.
2. Attach `HighflameConnectorDiscovery`.
3. **Security credentials** → **Create access key** (Application running outside AWS,
   unless Studio specifies otherwise).
4. Copy **Access key ID** and **Secret access key** once.

![Access keys](images/aws-03-access-keys.png)

## 3. Complete the connector in Studio

In Studio → **Registry → Connectors**, paste the values Studio asks for, for example:

| Studio field | AWS value |
| --- | --- |
| Role ARN | IAM role ARN (Option A) |
| Access key ID / Secret | From Option B, if used |
| Region | Region where agents run (e.g. `us-east-1`) |
| Account ID | 12-digit AWS account ID |

Save and wait for the connector status to become healthy.

## Verify

- Connector shows **Connected** / healthy in Studio.
- Discovered agents appear under the registry (see
  [Agent governance](../../recipes/agent-governance/)).
