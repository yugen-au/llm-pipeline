"""Smoke test for Langfuse integration.

Verifies that:
  1. The Langfuse SDK initializes from .env
  2. A trace + nested observations land in the configured Langfuse project
  3. Both span- and generation-typed observations work
  4. Flush + shutdown lifecycle is clean

Run: uv run python scripts/smoke_langfuse.py

Then check the Langfuse UI (Traces tab). You should see one trace named
"smoke_test" with two children: a span and a generation.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root regardless of cwd
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Fail loudly if creds are missing (smoke test is meaningless otherwise)
required = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")
missing = [k for k in required if not os.environ.get(k)]
if missing:
    print(f"Missing env vars: {missing}", file=sys.stderr)
    sys.exit(1)

from langfuse import Langfuse  # noqa: E402

# v4 SDK reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL from env
langfuse = Langfuse(
    environment="smoke-test",
)

with langfuse.start_as_current_observation(
    name="smoke_test",
    as_type="span",
    input={"reason": "verifying langfuse-migration branch wiring"},
) as root:
    with root.start_as_current_observation(
        name="fake_step",
        as_type="span",
        input={"step_name": "smoke_step"},
    ) as step_span:
        step_span.update(output={"completed": True})

    with root.start_as_current_observation(
        name="fake_llm_call",
        as_type="generation",
        model="claude-opus-4-7",
        input={"messages": [{"role": "user", "content": "hello"}]},
    ) as gen_span:
        gen_span.update(
            output="hello back",
            usage_details={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            cost_details={"total": 0.0001},
        )

    root.update(output={"smoke": "ok"})

# Critical: flush before exit so traces ship before the process dies
langfuse.flush()
langfuse.shutdown()

print("Smoke test complete.")
print(f"Open {os.environ['LANGFUSE_BASE_URL']} -> Traces -> look for 'smoke_test'")
