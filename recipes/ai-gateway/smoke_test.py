"""Smoke test for the ai-gateway recipe: one request through the gateway.

Exit 0 on success, 1 on failure, 2 when credentials are absent (skip).
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()
missing = [
    name
    for name in ("HIGHFLAME_API_KEY", "HIGHFLAME_GATEWAY_BASE_URL", "PROVIDER_API_KEY")
    if not os.environ.get(name)
]
if missing:
    print(f"SKIP: not set: {', '.join(missing)}")
    sys.exit(2)

from openai import OpenAI

try:
    client = OpenAI(
        base_url=os.environ["HIGHFLAME_GATEWAY_BASE_URL"],
        api_key=os.environ["PROVIDER_API_KEY"],  # forwarded upstream by the gateway
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
    print(f"FAIL: {type(exc).__name__}: {str(exc)[:200]}")
    sys.exit(1)
