import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agentconvos.parser as parser_module
import agentconvos.scanner as scanner_module
from agentconvos.app import _handoff_agent, _handoff_cmd, _resume_cmd, main
from agentconvos.parser import ConversationMeta, ConversationStats, get_meta, parse_jsonl
from agentconvos.scanner import Project, scan_projects


def _write_agy_db(path: Path, assistant_text: str = "I can help with that.") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE trajectory_meta (
                trajectory_id text,
                cascade_id text,
                trajectory_type integer,
                source integer,
                PRIMARY KEY (trajectory_id)
            );
            CREATE TABLE steps (
                idx integer,
                step_type integer NOT NULL DEFAULT 0,
                status integer NOT NULL DEFAULT 0,
                has_subtrajectory numeric NOT NULL DEFAULT false,
                metadata blob,
                error_details blob,
                permissions blob,
                task_details blob,
                render_info blob,
                step_payload blob,
                step_format integer NOT NULL DEFAULT 0,
                PRIMARY KEY (idx)
            );
            """
        )
        conn.execute(
            "INSERT INTO trajectory_meta VALUES (?, ?, ?, ?)",
            (path.stem, "cascade", 0, 0),
        )
        conn.execute(
            "INSERT INTO steps (idx, step_type, status, step_payload) VALUES (?, ?, ?, ?)",
            (0, 15, 5, f"\n^{assistant_text}2(bot-test".encode("utf-8")),
        )
        conn.commit()
    finally:
        conn.close()


def _write_agy_history(home: Path, conversation_id: str, workspace: Path) -> None:
    history = home / "history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "display": "start agy task",
            "timestamp": 1780436328708,
            "workspace": str(workspace),
            "conversationId": conversation_id,
        },
        {
            "display": "continue agy task",
            "timestamp": 1780436578579,
            "workspace": str(workspace),
            "conversationId": conversation_id,
        },
    ]
    history.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")


class CodexParserTests(unittest.TestCase):
    def test_text_parser_excludes_injected_project_instructions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout-session.jsonl"
            records = [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "session-id",
                        "timestamp": "2026-07-30T10:30:00Z",
                        "cwd": str(path.parent),
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "# AGENTS.md instructions for /tmp/project\n\n<INSTRUCTIONS>bootstrap</INSTRUCTIONS>",
                            }
                        ],
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "What changed in the release?",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "agent_message",
                        "message": "The release changed the retry behavior.",
                    },
                },
            ]
            path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )

            turns = parse_jsonl(path)

        self.assertEqual(
            [(turn.role, turn.text) for turn in turns],
            [
                ("user", "What changed in the release?"),
                ("assistant", "The release changed the retry behavior."),
            ],
        )

    def test_subagent_metadata_keeps_its_own_first_session_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout-child-session.jsonl"
            records = [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "child-session",
                        "session_id": "parent-session",
                        "parent_thread_id": "parent-session",
                        "timestamp": "2026-07-18T10:30:00Z",
                        "cwd": str(path.parent),
                    },
                },
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "parent-session",
                        "timestamp": "2026-07-17T10:30:00Z",
                        "cwd": str(path.parent),
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "Inspect the background worker",
                    },
                },
            ]
            path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )

            meta = get_meta(path)

        self.assertIsNotNone(meta)
        self.assertEqual(meta.uuid, "child-session")
        self.assertEqual(meta.timestamp, "2026-07-18T10:30:00Z")

    def test_text_parser_releases_json_records_as_it_streams(self):
        class TrackedRecord(dict):
            alive = 0
            peak = 0

            def __init__(self, value):
                super().__init__(value)
                type(self).alive += 1
                type(self).peak = max(type(self).peak, type(self).alive)

            def __del__(self):
                type(self).alive -= 1

        records = []
        for index in range(20):
            records.extend(
                (
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "message": f"Question number {index}",
                        },
                    },
                    {
                        "type": "event_msg",
                        "payload": {
                            "type": "agent_message",
                            "message": f"Assistant answer number {index}",
                        },
                    },
                )
            )
        pending = iter(records)

        def tracked_loads(_line):
            return TrackedRecord(next(pending))

        with (
            patch("builtins.open", return_value=io.StringIO("record\n" * len(records))),
            patch.object(parser_module.json, "loads", side_effect=tracked_loads),
        ):
            turns = parser_module._parse_jsonl_codex(Path("/tmp/session.jsonl"))

        self.assertEqual(len(turns), 40)
        self.assertLessEqual(TrackedRecord.peak, 3)


class ClaudeParserTests(unittest.TestCase):
    def test_text_parser_excludes_local_command_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claude-session.jsonl"
            records = [
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": "Please inspect the retry behavior.",
                    },
                },
                {
                    "type": "user",
                    "isMeta": True,
                    "message": {
                        "role": "user",
                        "content": "<local-command-caveat>generated locally</local-command-caveat>",
                    },
                },
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": "<command-name>/model</command-name>",
                    },
                },
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": "<local-command-stdout>Set model</local-command-stdout>",
                    },
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "The retry behavior is unchanged.",
                            }
                        ],
                    },
                },
            ]
            path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )

            turns = parse_jsonl(path)

        self.assertEqual(
            [(turn.role, turn.text) for turn in turns],
            [
                ("user", "Please inspect the retry behavior."),
                ("assistant", "The retry behavior is unchanged."),
            ],
        )


class ScannerCacheTests(unittest.TestCase):
    def test_old_metadata_cache_is_invalidated_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "meta-cache.json"
            cache_path.write_text(
                json.dumps({"/tmp/session.jsonl": {"uuid": "stale-parent"}}),
                encoding="utf-8",
            )

            with patch.object(scanner_module, "_CACHE_PATH", cache_path):
                self.assertEqual(scanner_module._load_cache(), {})
                scanner_module._save_cache(
                    {"/tmp/session.jsonl": {"uuid": "child-session"}}
                )
                reloaded = scanner_module._load_cache()

            persisted = json.loads(cache_path.read_text(encoding="utf-8"))

        self.assertEqual(
            reloaded,
            {"/tmp/session.jsonl": {"uuid": "child-session"}},
        )
        self.assertEqual(persisted["__version__"], 2)


class HandoffCommandTests(unittest.TestCase):
    def test_codex_handoff_can_use_yolo(self):
        self.assertEqual(
            _handoff_cmd("codex", "handoff message", codex_yolo=True),
            ["codex", "--yolo", "handoff message"],
        )

    def test_yolo_does_not_force_codex_target(self):
        self.assertEqual(_handoff_agent("agy", None, True), "agy")
        self.assertEqual(_handoff_agent("claude", None, True), "claude")
        self.assertEqual(_handoff_agent("agy", "codex", True), "codex")

    def test_handoff_agent_targets_codex_independent_of_conversation_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            convo_path = cwd / "conversation.jsonl"
            convo_path.write_text("", encoding="utf-8")
            meta = ConversationMeta(
                path=convo_path,
                uuid="abc123",
                slug="claude-source",
                timestamp="2026-06-03T12:00:00",
                cwd=str(cwd),
                preview="Previous work",
                source="claude",
            )
            project = Project("tmp", str(cwd), [meta])

            old_argv = sys.argv
            old_cwd = os.getcwd()
            sys.argv = [
                "agentconvos",
                "--handoff",
                "--handoff-agent",
                "codex",
                "--yolo",
                "--dry-run",
            ]
            stream = io.StringIO()
            try:
                os.chdir(cwd)
                with (
                    patch("agentconvos.scanner.scan_projects", return_value=[project]),
                    patch("agentconvos.app.parse_jsonl", return_value=[]),
                    patch("agentconvos.app.get_stats", return_value=ConversationStats()),
                    patch("agentconvos.app.to_markdown", return_value="exported"),
                    contextlib.redirect_stdout(stream),
                ):
                    main()
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)

        output = stream.getvalue()
        self.assertIn("codex --yolo", output)
        self.assertNotIn("claude --dangerously-skip-permissions", output)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", output)

    def test_agy_handoff_yolo_without_target_stays_agy(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            convo_path = cwd / "agy.db"
            _write_agy_db(convo_path)
            meta = ConversationMeta(
                path=convo_path,
                uuid="agy123",
                slug="",
                timestamp="2026-06-03T12:00:00",
                cwd=str(cwd),
                preview="Previous Agy work",
                source="agy",
            )
            project = Project("agy:tmp", f"[agy] {cwd}", [meta])

            old_argv = sys.argv
            old_cwd = os.getcwd()
            sys.argv = ["agentconvos", "--handoff", "agy", "--yolo", "--dry-run"]
            stream = io.StringIO()
            try:
                os.chdir(cwd)
                with (
                    patch("agentconvos.scanner.scan_projects", return_value=[project]),
                    patch("agentconvos.app.parse_jsonl", return_value=[]),
                    patch("agentconvos.app.get_stats", return_value=ConversationStats()),
                    patch("agentconvos.app.to_markdown", return_value="exported"),
                    contextlib.redirect_stdout(stream),
                ):
                    main()
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)

        output = stream.getvalue()
        self.assertIn("agy --dangerously-skip-permissions", output)
        self.assertNotIn("codex --yolo", output)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", output)

    def test_convo_source_can_handoff_to_codex_yolo(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            convo_path = cwd / "agy.db"
            _write_agy_db(convo_path)
            meta = ConversationMeta(
                path=convo_path,
                uuid="agy123",
                slug="",
                timestamp="2026-06-03T12:00:00",
                cwd=str(cwd),
                preview="Previous Agy work",
                source="agy",
            )
            project = Project("agy:tmp", f"[agy] {cwd}", [meta])

            old_argv = sys.argv
            old_cwd = os.getcwd()
            sys.argv = [
                "agentconvos",
                "--convo",
                "agy",
                "--handoff",
                "codex",
                "--yolo",
                "--dry-run",
            ]
            stream = io.StringIO()
            try:
                os.chdir(cwd)
                with (
                    patch("agentconvos.scanner.scan_projects", return_value=[project]),
                    patch("agentconvos.app.parse_jsonl", return_value=[]),
                    patch("agentconvos.app.get_stats", return_value=ConversationStats()),
                    patch("agentconvos.app.to_markdown", return_value="exported"),
                    contextlib.redirect_stdout(stream),
                ):
                    main()
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)

        output = stream.getvalue()
        self.assertIn("Exported: agy123", output)
        self.assertIn("codex --yolo", output)
        self.assertNotIn("agy --dangerously-skip-permissions", output)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", output)

    def test_convo_source_can_handoff_to_claude_yolo(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            convo_path = cwd / "agy.db"
            _write_agy_db(convo_path)
            meta = ConversationMeta(
                path=convo_path,
                uuid="agy123",
                slug="",
                timestamp="2026-06-03T12:00:00",
                cwd=str(cwd),
                preview="Previous Agy work",
                source="agy",
            )
            project = Project("agy:tmp", f"[agy] {cwd}", [meta])

            old_argv = sys.argv
            old_cwd = os.getcwd()
            sys.argv = [
                "agentconvos",
                "--convo",
                "agy",
                "--handoff",
                "claude",
                "--yolo",
                "--dry-run",
            ]
            stream = io.StringIO()
            try:
                os.chdir(cwd)
                with (
                    patch("agentconvos.scanner.scan_projects", return_value=[project]),
                    patch("agentconvos.app.parse_jsonl", return_value=[]),
                    patch("agentconvos.app.get_stats", return_value=ConversationStats()),
                    patch("agentconvos.app.to_markdown", return_value="exported"),
                    contextlib.redirect_stdout(stream),
                ):
                    main()
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)

        output = stream.getvalue()
        self.assertIn("claude --dangerously-skip-permissions", output)
        self.assertNotIn("Error: --yolo only applies to Codex", output)

    def test_agy_handoff_and_resume_commands(self):
        self.assertEqual(
            _handoff_cmd("agy", "handoff message"),
            ["agy", "--dangerously-skip-permissions", "--prompt-interactive", "handoff message"],
        )
        self.assertEqual(
            _resume_cmd("agy", "abc123", ["--sandbox"]),
            ["agy", "--dangerously-skip-permissions", "--sandbox", "--conversation", "abc123"],
        )


class TranscriptExportTests(unittest.TestCase):
    def test_turns_json_exports_normalized_back_and_forth(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout-session.jsonl"
            records = [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "session-id",
                        "timestamp": "2026-07-30T10:30:00Z",
                        "cwd": str(path.parent),
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "What changed?",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "agent_message",
                        "message": "Only the retry behavior changed.",
                    },
                },
            ]
            path.write_text(
                "\n".join(json.dumps(record) for record in records),
                encoding="utf-8",
            )

            old_argv = sys.argv
            sys.argv = ["agentconvos", "--turns", str(path), "--json"]
            stream = io.StringIO()
            try:
                with (
                    patch("agentconvos.app.ConvoExplorer.run"),
                    contextlib.redirect_stdout(stream),
                ):
                    main()
            finally:
                sys.argv = old_argv

        output = stream.getvalue()
        self.assertIn('"turns"', output)
        payload = json.loads(output)
        self.assertEqual(payload["conversation"]["uuid"], "session-id")
        self.assertEqual(payload["conversation"]["source"], "codex")
        self.assertEqual(payload["detail"], "text")
        self.assertEqual(
            payload["turns"],
            [
                {"index": 0, "role": "user", "text": "What changed?"},
                {
                    "index": 1,
                    "role": "assistant",
                    "text": "Only the retry behavior changed.",
                },
            ],
        )


class AgyConversationTests(unittest.TestCase):
    def test_agy_db_uses_history_for_metadata_and_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agy_home = root / "antigravity-cli"
            workspace = root / "project"
            workspace.mkdir()
            conversation_id = "12345678-1234-4321-9876-123456789abc"
            db_path = agy_home / "conversations" / f"{conversation_id}.db"
            _write_agy_db(db_path, "I can help with the agy task.")
            _write_agy_history(agy_home, conversation_id, workspace)

            with patch.dict(os.environ, {"AGY_HOME": str(agy_home)}):
                meta = get_meta(db_path)
                turns = parse_jsonl(db_path)

        self.assertIsNotNone(meta)
        assert meta is not None
        self.assertEqual(meta.source, "agy")
        self.assertEqual(meta.uuid, conversation_id)
        self.assertEqual(meta.cwd, str(workspace))
        self.assertEqual(meta.preview, "start agy task")
        self.assertEqual(meta.timestamp, "2026-06-02T21:38:48.708000Z")
        self.assertEqual([t.role for t in turns], ["user", "user", "assistant"])
        self.assertIn("continue agy task", turns[1].text)
        self.assertIn("I can help with the agy task.", turns[2].text)

    def test_scan_projects_discovers_agy_conversations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agy_home = root / "antigravity-cli"
            workspace = root / "project"
            workspace.mkdir()
            conversation_id = "12345678-1234-4321-9876-123456789abc"
            _write_agy_db(agy_home / "conversations" / f"{conversation_id}.db")
            _write_agy_history(agy_home, conversation_id, workspace)

            with (
                patch.dict(os.environ, {"AGY_HOME": str(agy_home)}),
                patch("agentconvos.scanner._CACHE_PATH", root / "meta-cache.json"),
            ):
                projects = scan_projects(source="agy")

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].display_path, f"[agy] {workspace}")
        self.assertEqual(projects[0].conversations[0].source, "agy")


if __name__ == "__main__":
    unittest.main()
