# Microsoft Copilot Studio Connector Setup

This guide explains how to configure **Microsoft Copilot Studio** for the Highflame Registry connector.

Discovery is read-only. Highflame enumerates Copilot Studio (and Microsoft 365 Copilot Agent Builder) agents in your Power Platform tenant. Nothing is written to Entra, Power Platform, or Dataverse.

Use the **same Entra app registration** as the [Microsoft Entra connector](entra.md). Connecting in Studio uses the same Tenant ID, Client ID, and client secret.

![Microsoft Entra connector configuration](images/entra_connector.png)

---

## Step 1 — Reuse the Entra App Registration

Do **not** create a second app. Open the registration you already use for Entra discovery (often named `Highflame Discovery`):

**Azure Portal → Microsoft Entra ID → App registrations**

You need:

```text
Directory (tenant) ID
Application (client) ID
Client secret Value
```

If that app does not exist yet, complete [entra.md](entra.md) first (Graph permissions, admin consent, client secret), then return here.

> **Important:** The Highflame Copilot connector is a **different provider** from Entra. In Studio, pick **Copilot Studio**. Do not add an Entra connector and name it `copilot` — that still enumerates Entra identities, not Copilot Studio agents.

---

## Step 2 — Power Platform Access (to list agents)

The same app must be able to obtain a Power Platform token. Connecting still succeeds with **zero agents** if Copilot Studio is unused in the tenant; listing agents needs admin on Power Platform.

Grant the enterprise application the **Power Platform Administrator** directory role (Entra ID → Roles and administrators), or register it as a Power Platform management app (`New-PowerAppManagementApp` / BAP `adminApplications`).

To list bots from Dataverse (fallback when the inventory API is unavailable for app-only tokens):

1. [Power Platform admin center](https://admin.powerplatform.microsoft.com/environments) → the environment that hosts Copilot Studio (often **Default**).
2. That environment must have **Dataverse**.
3. **Settings → Users + permissions → Application users → New app user**.
4. Add the same app → business unit of that environment → security role **System Administrator**.

If you are not a Dataverse System Administrator yourself, Entra Global Admin is not enough to assign that role in the UI. A tenant admin can self-elevate with Power Platform CLI:

```powershell
pac auth create
pac admin self-elevate --environment <environment-id>
```

Then add the application user.

---

## Step 3 — Configure the Highflame Connector

Open:

**Highflame → Registry → Connections → Connect provider**

Select:

```text
Provider:
Copilot Studio
```

Fill in the connector:

```text
Name:
Corp Copilot Studio

Tenant ID:
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

Client ID:
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

Client secret:
<client secret VALUE>
```

These three values are the same as the Entra connector. Then click **Add connector** and **Sync now**.

---

## Step 4 — Review What Arrived

Discovered Copilot agents land as **discovered** identities.

- Open **Registry → Unmanaged** (Adoption Inbox).
- Do **not** expect them on **Registry → Inventory** with Status **Active / Pending / Expired** — that view hides `discovered`.

A sync of **OK** with **zero agents** still means connected when the tenant has no Copilot Studio inventory yet.

---

## Connector Configuration Summary

| Highflame Field   | Microsoft Value                          |
| ----------------- | ---------------------------------------- |
| **Provider**      | Copilot Studio                           |
| **Name**          | Customer-defined name                    |
| **Tenant ID**     | Directory (tenant) ID                    |
| **Client ID**     | Application (client) ID                  |
| **Client secret** | Client secret **Value** (same as Entra)  |

---

## Optional — Create a Test Agent

To prove a live row (not only an empty sync):

1. Assign **Microsoft Copilot Studio Viral Trial** (or a paid Copilot Studio license) to the user who will create the agent. Do not buy extra packs only for this test.
2. Open [Copilot Studio](https://copilotstudio.microsoft.com) in the **Default** (or Dataverse) environment.
3. Create and save an agent with a unique name.
4. **Sync now** on the Copilot connector, then check **Unmanaged**.

---

## Security Notes

* Discovery never writes to your IdP or Dataverse.
* Reuse one Entra app for Entra + Copilot; do not duplicate secrets.
* Do not use the **Object ID** as the Client ID, or the **Secret ID** as the secret.
* Never commit the client secret to source control.
* Adding Dataverse to Default is billable in some tenants — only do it if you need agents listed from the `bots` table.
