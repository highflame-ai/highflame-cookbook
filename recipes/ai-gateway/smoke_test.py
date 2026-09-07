"""Smoke test for the ai-gateway recipe: one request through the gateway.

Exit 0 on success, 1 on failure, 2 when credentials are absent (skip).
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# CI sets HIGHFLAME_API_KEY and OPENAI_API_KEY, not the gateway variables, so default the base
# URL and fall back to the provider key CI does have. Without this the test always skipped and
# the recipe was never exercised.
GATEWAY = os.environ.get("HIGHFLAME_GATEWAY_BASE_URL") or "https://gateway.highflame.ai/llm/v1"
PROVIDER_KEY = os.environ.get("PROVIDER_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""

missing = [n for n, v in (("HIGHFLAME_API_KEY", os.environ.get("HIGHFLAME_API_KEY")),
                          ("PROVIDER_API_KEY or OPENAI_API_KEY", PROVIDER_KEY)) if not v]
if missing:
    print(f"SKIP: not set: {', '.join(missing)}")
    sys.exit(2)

from openai import OpenAI

try:
    client = OpenAI(
        base_url=GATEWAY,
        api_key=PROVIDER_KEY,  # forwarded upstream by the gateway
        default_headers={"X-Highflame-APIKey": os.environ["HIGHFLAME_API_KEY"]},
    )
    reply = client.chat.completions.create(
        model=os.environ.get("MODEL_ID", "openai/gpt-4o-mini"),
        messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        max_tokens=5,
    )
    text = (reply.choices[0].message.content or "").strip()
    assert text, "the gateway returned an empty completion"
    print(f"OK: reached the model through the gateway, reply={text[:20]!r}")
except Exception as exc:  # noqa: BLE001
    # Type and status only. A provider's 401 body can embed a masked form of the rejected key,
    # which GitHub Actions secret masking will not match.
    status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    print(f"FAIL: {type(exc).__name__}" + (f" (HTTP {status})" if status else ""))
    sys.exit(1)
