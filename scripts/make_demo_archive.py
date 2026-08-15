"""Build a small synthetic conversation archive for the README images.

Every conversation here is invented. The point is to run the real
agentconvos against a real archive layout, so the screenshots show
genuine program output without publishing anyone's private sessions.

Usage:
    python scripts/make_demo_archive.py /tmp/demohome
"""

import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path(sys.argv[1])
if HOME.exists():
    shutil.rmtree(HOME)


def stamps(started, count):
    """Space the turns a few minutes apart, starting at `started`."""
    base = datetime.fromisoformat(started)
    return [(base + timedelta(minutes=7 * i)).isoformat() for i in range(count)]


def project(name):
    """The commands report on a directory, so it has to actually exist."""
    path = HOME / "work" / name
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def claude_session(cwd, slug, uuid, branch, started, turns):
    """turns is a list of (user_text, assistant_text)."""
    d = HOME / ".claude" / "projects" / cwd.replace("/", "-")
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for (user_text, assistant_text), ts in zip(
        turns, stamps(started, len(turns)), strict=True
    ):
        lines.append({
            "type": "user",
            "timestamp": ts,
            "cwd": cwd,
            "gitBranch": branch,
            "slug": slug,
            "message": {"role": "user", "content": user_text},
        })
        lines.append({
            "type": "assistant",
            "timestamp": ts,
            "cwd": cwd,
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


def codex_session(cwd, uuid, started, turns):
    d = HOME / ".codex" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "type": "session_meta",
            "timestamp": started,
            "payload": {"id": uuid, "timestamp": started, "cwd": cwd},
        },
        {
            "type": "turn_context",
            "timestamp": started,
            "payload": {"model": "gpt-5.4-codex", "reasoning_effort": "high"},
        },
    ]
    for (user_text, assistant_text), ts in zip(
        turns, stamps(started, len(turns)), strict=True
    ):
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


checkout = project("checkout-service")
billing = project("billing-api")
infra = project("platform-infra")

# --- checkout-service ---------------------------------------------------

claude_session(
    checkout, "jwt-refresh-race", "019e7f21-4c8a-7b31-9d2c-11ab4e77c001",
    "fix/jwt-refresh", "2026-05-31T14:30:00",
    [
        ("Two requests refreshing the JWT at the same time both get a 401. "
         "Can you find the race?",
         "The refresh handler reads the old token, mints a new one, then writes "
         "it back. Two requests interleave between the read and the write."),
        ("Fix it with a lock scoped per user, not a global one.",
         "Added a per-user mutex keyed on the subject claim."),
        ("Add a test that fails without the lock.",
         "Fires 20 concurrent refreshes for one user and asserts a single token."),
    ],
)

codex_session(
    checkout, "019e783a-e2bb-7ec2-9d2c-def97ab8c003", "2026-05-30T09:15:00",
    [
        ("Add rate limiting to the public API.",
         "Token bucket per API key, 100 a minute."),
        ("What happens when Redis is down?",
         "Every request fails closed with a 503. I would rather fail open and log."),
    ],
)

claude_session(
    checkout, "soft-deletes", "019e7c04-9f13-7a55-8e41-22cd9b13d002",
    "db/user-schema", "2026-05-29T16:40:00",
    [
        ("We need to migrate the user table to the new schema. Walk me through "
         "the options for deletes.",
         "Three options: hard delete with an audit table, a deleted_at column, "
         "or a separate archive table. A deleted_at column keeps the foreign "
         "keys intact."),
        ("Go with soft deletes. Write the migration.",
         "Adds a nullable deleted_at column and a partial index on active rows."),
    ],
)

# --- billing-api --------------------------------------------------------

claude_session(
    billing, "stripe-webhook-retries", "019e7a55-1d92-7c18-bb03-44ef1a92e004",
    "fix/webhook-retries", "2026-05-28T11:05:00",
    [
        ("Stripe is retrying webhooks we already handled and we double charge.",
         "The handler acknowledges after the charge instead of before, so a "
         "slow response looks like a failure to Stripe."),
        ("Make it idempotent on the event id.",
         "Stores each event id before the charge and returns 200 on a repeat."),
    ],
)

codex_session(
    billing, "019e7b31-77c2-7ab4-9f10-55da2b41c005", "2026-05-27T15:20:00",
    [
        ("Why is the invoice PDF job using 4GB of memory?",
         "It loads every line item into memory before rendering. A cursor over "
         "the line items keeps it flat at about 90MB."),
        ("Add a rate limit for the PDF job.",
         "Streams the line items and caps the job at 10 renders a second."),
    ],
)

# --- platform-infra -----------------------------------------------------

claude_session(
    infra, "terraform-drift", "019e79c8-3ba1-7d67-8c22-66fb3c52e006",
    "main", "2026-05-26T08:45:00",
    [
        ("terraform plan shows drift on the security groups every morning.",
         "An autoscaling policy rewrites the ingress rules outside Terraform, "
         "so the state is correct and the cloud is not."),
        ("Can we stop the fight without turning off the policy?",
         "Move the ingress rules to their own resource and ignore changes on it."),
    ],
)

codex_session(
    infra, "019e7812-9ee4-7f03-a145-77bc4d63e007", "2026-05-25T17:30:00",
    [
        ("The nightly backup job silently stopped three weeks ago.",
         "The cron entry still runs, but the upload fails on an expired token "
         "and the script swallows the error."),
        ("Make it fail loudly and page us.",
         "The script exits non-zero on upload failure and posts to the alert "
         "channel."),
    ],
)

count = sum(1 for _ in (HOME / ".claude" / "projects").rglob("*.jsonl"))
count += sum(1 for _ in (HOME / ".codex" / "sessions").rglob("*.jsonl"))
print(f"archive built at {HOME} with {count} conversations")
