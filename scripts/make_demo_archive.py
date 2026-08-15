"""Build a small synthetic conversation archive for the README demo.

Everything here is invented. The point is to run the real agentconvos
against a real archive layout without putting private conversations in a
public screenshot.
"""

import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path


def stamps(started, count):
    """Space the turns a few minutes apart, starting at `started`."""
    base = datetime.fromisoformat(started)
    return [(base + timedelta(minutes=7 * i)).isoformat() for i in range(count)]

HOME = Path(sys.argv[1])

if HOME.exists():
    shutil.rmtree(HOME)

# --context reports on the directory you are standing in, so the project has
# to exist and the records have to point at it.
PROJECT_DIR = HOME / "work" / "checkout-service"
PROJECT_DIR.mkdir(parents=True)
PROJECT = str(PROJECT_DIR)


def claude_session(slug, uuid, branch, started, turns):
    """turns is a list of (user_text, assistant_text)."""
    d = HOME / ".claude" / "projects" / PROJECT.replace("/", "-")
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for (user_text, assistant_text), ts in zip(turns, stamps(started, len(turns)), strict=True):
        lines.append({
            "type": "user",
            "timestamp": ts,
            "cwd": PROJECT,
            "gitBranch": branch,
            "slug": slug,
            "message": {"role": "user", "content": user_text},
        })
        lines.append({
            "type": "assistant",
            "timestamp": ts,
            "cwd": PROJECT,
            "gitBranch": branch,
            "effort": "high",
            "message": {
                "role": "assistant",
                "model": "claude-opus-4-6",
                "usage": {"input_tokens": 41200, "output_tokens": 1850},
                "content": [{"type": "text", "text": assistant_text}],
            },
        })
    (d / f"{uuid}.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
    )


def codex_session(uuid, started, turns):
    d = HOME / ".codex" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "type": "session_meta",
            "timestamp": started,
            "payload": {"id": uuid, "timestamp": started, "cwd": PROJECT},
        },
        {
            "type": "turn_context",
            "timestamp": started,
            "payload": {"model": "gpt-5.4-codex", "reasoning_effort": "high"},
        },
    ]
    for (user_text, assistant_text), ts in zip(turns, stamps(started, len(turns)), strict=True):
        lines.append({
            "type": "event_msg",
            "timestamp": ts,
            "payload": {"type": "user_message", "message": user_text},
        })
        lines.append({
            "type": "response_item",
            "timestamp": ts,
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": assistant_text}],
            },
        })
    (d / f"rollout-{started[:10]}T09-15-00-{uuid}.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
    )


claude_session(
    "jwt-refresh-race", "019e7f21-4c8a-7b31-9d2c-11ab4e77c001",
    "fix/jwt-refresh", "2026-05-31T14:30:00",
    [
        ("Two requests refreshing the JWT at the same time both get a 401. "
         "Can you find the race?",
         "The refresh handler reads the old token, mints a new one, then writes it "
         "back. Two requests interleave between the read and the write, so the "
         "second one invalidates the first request's fresh token."),
        ("Fix it with a lock scoped per user, not a global one.",
         "Added a per-user mutex keyed on the subject claim. Concurrent refreshes "
         "for different users still run in parallel."),
        ("Add a test that fails without the lock.",
         "Fires 20 concurrent refreshes for one user and asserts a single token."),
    ],
)

claude_session(
    "soft-deletes", "019e7c04-9f13-7a55-8e41-22cd9b13d002",
    "db/user-schema", "2026-05-29T16:40:00",
    [
        ("We need to migrate the user table to the new schema. Walk me through "
         "the options for deletes.",
         "Three options: hard delete with an audit table, a deleted_at column, or "
         "a separate archive table. A deleted_at column keeps foreign keys intact "
         "and is the least disruptive for the reporting queries."),
        ("Go with soft deletes. Write the migration.",
         "Adds a nullable deleted_at column and a partial index on active rows."),
    ],
)

codex_session(
    "019e783a-e2bb-7ec2-9d2c-def97ab8c003", "2026-05-30T09:15:00",
    [
        ("Add rate limiting to the public API endpoints.",
         "Added a token bucket per API key, 100 requests a minute with a burst of "
         "20. Limits are stored in Redis so they hold across instances."),
        ("What happens when Redis is down?",
         "Every request fails closed with a 503. I would rather fail open and log."),
    ],
)

print(f"archive built at {HOME}")
