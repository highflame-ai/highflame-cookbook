# Safari Browser Security Setup

This guide explains how to install and connect **Highflame Browser Security** in
**Safari** on macOS.

Safari does not load a Chrome-style unpacked folder. The extension ships as the
**Highflame Browser Security** macOS app (App Store or a signed build from
Highflame). You enable the Safari Web Extension from that app, then connect it
with the same API key and endpoints as Chrome and Firefox.

---

## Step 1 — Create a Highflame API Key

Sign in to **Highflame Studio**:

[https://studio.highflame.ai](https://studio.highflame.ai)

Go to:

**Web AI → API Keys → Create**

![API key](images/api_key.png)

Create a service key. The value starts with:

```text
zid_sk_
```

Copy the key when it is created and store it securely. You will paste it into the
extension in Step 4.

> **Important:** Copy the key when it is created. Highflame does not show the full
> value again. Do not commit it to source control or share it through Slack/email.

---

## Step 2 — Install the Highflame Browser Security App

Install **Highflame Browser Security** from the Mac App Store, or open the signed
`.app` your Highflame contact provides.

Launch the app once. On macOS it reports whether the Safari extension is on or
off, and offers:

```text
Quit and Open Safari Extensions Preferences…
```

Click that button, or open Safari yourself and continue to Step 3.

---

## Step 3 — Enable the Extension in Safari

In Safari:

**Safari → Settings → Extensions**

(Safari 16 and earlier: **Safari → Settings → Extensions**, or
**Safari → Preferences → Extensions**.)

Enable:

```text
Highflame Browser Security
```

Grant website access for the AI sites you want protected. For full coverage,
allow the extension on all websites. If Safari asks on first visit to ChatGPT or
Claude, choose **Always Allow on This Website**.

Confirm the toolbar icon is visible:

```text
Safari toolbar → Highflame Browser Security
```

If the icon is missing: **View → Customize Toolbar** and drag it in.

---

## Step 4 — Connect the Extension

Click the **Highflame Browser Security** icon in the Safari toolbar.

Click **Settings**.

Fill in:

```text
API Key:
zid_sk_<your key>

Shield Endpoint:
https://api.highflame.ai

Token Endpoint:
https://studio.highflame.ai/api/cli-auth/token
```

Click **Save**.

After that, check whether the session is visible.
**Web AI → Sessions/Events**

## Connector Configuration Summary

| Extension field | Value |
| --- | --- |
| **API Key** | Studio service key (`zid_sk_…`) |
| **Shield Endpoint** (SaaS) | `https://api.highflame.ai` |
| **Token Endpoint** (SaaS) | `https://studio.highflame.ai/api/cli-auth/token` |
| **Shield Endpoint** (self-hosted) | Your Shield base URL |
| **Token Endpoint** (self-hosted) | Your Studio `/api/cli-auth/token` URL |
| **Safari enablement** | Safari → Settings → Extensions → on, with website access |

---

## Security Notes

* Use a dedicated Studio service key for the browser extension.
* Never commit the API key to source control.
* Do not paste the key into Slack, email, or screenshots.
* Custom Shield and Token URLs must be `https://`.
* Grant Safari website access only as broadly as your policy requires.
* Rotate the key according to your organization's policy.
