# GitHub Copilot with Highflame AI Gateway

## Overview

This cookbook shows how to configure **GitHub Copilot Chat in VS Code** to use the **Highflame AI Gateway**.

With this setup, Copilot Chat requests are routed through Highflame instead of directly to the underlying model provider. It uses VS Code's built-in **Custom Endpoint** (bring-your-own-key) provider — no debug flags or extension hacks.

```text
┌──────────────────────┐
│  Copilot Chat        │
│  VS Code / Device    │
└──────────┬───────────┘
           │
           │ Responses / Chat Completions API
           ▼
┌──────────────────────────┐
│   Highflame AI Gateway   │
│                          │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│       AI Model           │
│    Configured in         │
│    Highflame Gateway     │
└──────────────────────────┘
```

> **Scope:** Custom endpoints cover **Copilot Chat and agent mode**. Inline code completions (ghost text) still go to GitHub's own infrastructure and are not routed through the gateway.

---

# 1. Prerequisites

* **VS Code** with the **GitHub Copilot Chat** extension installed.
* On **Copilot Business / Enterprise** plans, an administrator must enable the **"Bring Your Own Language Model Key in VS Code"** policy in the Copilot policy settings on GitHub.com. Individual plans (Free / Pro / Pro+) can use it directly.

---

# 2. Get Your Highflame Gateway Details

Log in to **Highflame Studio**:

[Highflame Studio](https://studio.highflame.ai)

You will need three values to configure Copilot:

* **LLM Base URL**
* **API Key**
* **Model**

## 2.1 Get the LLM Base URL

After logging in:

1. Open **AI Gateway**.
2. Select **LLM Providers** from the left navigation.
3. At the top of the **Providers** page, locate **LLM Base URL**.
4. Copy the displayed URL.

For example:

```text
https://gateway.highflame.ai/llm/v1
```

Use this value as the model `url` in your Copilot configuration.

> **Note:** Use the LLM Base URL displayed in your Highflame Studio environment. The URL may differ between environments.

## 2.2 Create an API Key

1. In Highflame Studio, open **AI Gateway → API Keys**.
2. Click **Create API Key**.
3. Create a new API key.
4. Copy the API key and store it securely.

![api\_key](images/api_key.png)

The API key is used to authenticate Copilot requests with the Highflame AI Gateway. VS Code sends it as an `Authorization: Bearer` header.

> **Important:** Do not paste the API key into a settings file that is committed to Git. VS Code stores it in secret storage when you enter it through the setup flow (see step 3).

## 2.3 Identify the Model

Use the model identifier configured and available through your Highflame AI Gateway, prefixed with the provider.

For example:

```text
openai/gpt-5.6-sol
```

Use the exact model identifier configured in your Highflame environment.

## 2.4 Information You Should Have

Before continuing to the Copilot configuration, you should have:

| Value                  | Example                               |
| ---------------------- | ------------------------------------- |
| Highflame LLM Base URL | `https://gateway.highflame.ai/llm/v1` |
| Highflame API Key      | `YOUR_HIGHFLAME_API_KEY`              |
| Model                  | `openai/gpt-5.6-sol`                  |

You will use these values in the next step to configure Copilot.

---

# 3. Configure Copilot

1. Open the Command Palette (`Cmd/Ctrl + Shift + P`).
2. Run **Chat: Manage Language Models**.
3. Choose **Add Models → Custom Endpoint**.
4. When prompted, enter the **Highflame API Key**. VS Code stores it in secret storage and references it as an input variable — the raw key never lands in a config file.

VS Code then opens a dedicated **`chatLanguageModels.json`** file where the provider and models are defined. Configure it like this:

```json
{
    "name": "highflame",
    "vendor": "customendpoint",
    "apiKey": "${input:chat.lm.secret.XXXXXXXX}",
    "apiType": "responses",
    "models": [
        {
            "id": "YOUR_MODEL",
            "name": "YOUR_MODEL",
            "url": "https://YOUR-HIGHFLAME-GATEWAY/llm/v1",
            "toolCalling": true,
            "vision": true,
            "maxInputTokens": 128000,
            "maxOutputTokens": 16000
        }
    ]
}
```

Configuration notes:

* `apiKey` — leave the `${input:...}` reference exactly as VS Code generated it. It resolves from secret storage at request time.
* `apiType` — the Highflame AI Gateway supports both `responses` and `chat-completions` (both verified working). Pick whichever your model/provider setup expects; `chat-completions` is VS Code's default when the field is omitted.
* `toolCalling: true` — required for the model to be usable in agent mode.
* `maxInputTokens` / `maxOutputTokens` — their sum must not exceed the model's actual context window.

---

# 4. Replace the Configuration Values

Replace:

```text
YOUR_MODEL
```

with the model configured in your Highflame Gateway.

For example:

```json
"id": "openai/gpt-5.6-sol",
"name": "openai/gpt-5.6-sol",
```

Replace:

```text
https://YOUR-HIGHFLAME-GATEWAY/llm/v1
```

with your Highflame Gateway endpoint.

For example:

```json
"url": "https://gateway.highflame.ai/llm/v1"
```

The final configuration might look like:

```json
{
    "name": "highflame",
    "vendor": "customendpoint",
    "apiKey": "${input:chat.lm.secret.XXXXXXXX}",
    "apiType": "responses",
    "models": [
        {
            "id": "openai/gpt-5.6-sol",
            "name": "openai/gpt-5.6-sol",
            "url": "https://gateway.highflame.ai/llm/v1",
            "toolCalling": true,
            "vision": true,
            "maxInputTokens": 128000,
            "maxOutputTokens": 16000
        }
    ]
}
```

---

# 5. Select the Model in Copilot Chat

1. Open the **Copilot Chat** panel.
2. Open the **model picker** at the bottom of the chat input.
3. Select the model you configured (e.g. `openai/gpt-5.6-sol`).

> **Note:** If the newly added model does not appear in the picker, restart VS Code.

Requests will now follow:

```text
Copilot Chat
     ↓
Highflame AI Gateway
     ↓
Configured Model
```

---

# 6. Verify the Connection

Inside Copilot Chat, run a simple request:

```text
Hello, confirm that the connection is working.
```

Then check **Highflame Observatory**.

You should see the request being received by Highflame.

A successful request confirms:

```text
Copilot Chat
     ↓
Highflame API authentication
     ↓
Highflame Gateway
     ↓
Model routing
     ↓
Model response
     ↓
Copilot Chat
```

If the request fails with an authentication error, verify that the API key entered in step 3 is a valid Highflame API key — it is sent to the gateway as an `Authorization: Bearer` header.

---

# 7. Copilot CLI (optional)

The Copilot CLI supports the same routing through environment variables:

```bash
export COPILOT_PROVIDER_BASE_URL="https://gateway.highflame.ai/llm/v1"
export COPILOT_PROVIDER_API_KEY="YOUR_HIGHFLAME_API_KEY"
export COPILOT_MODEL="openai/gpt-5.6-sol"
```

---

# 8. Summary

After completing the setup, customers can use Copilot Chat normally.

The only difference is where chat requests are routed:

```text
Before:

Copilot Chat → GitHub / Model Provider


After:

Copilot Chat → Highflame AI Gateway → Model Provider
```

Highflame becomes the centralized gateway between Copilot Chat and the configured AI models while the customer continues using the normal Copilot experience. Inline code completions remain on GitHub's infrastructure.
