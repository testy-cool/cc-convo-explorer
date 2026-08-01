import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentconvos.parser import _detect_format, get_meta, parse_jsonl
from agentconvos import scanner


THREAD_ID = "019f0000-0000-7000-8000-000000000001"


def _thread_lines(thread_id: str = THREAD_ID) -> list[str]:
    return [
        json.dumps(
            {
                "type": "cmdmint_thread",
                "schemaVersion": 1,
                "id": thread_id,
                "title": "Find the MCP selector conversation",
                "scope": "agentconvos",
                "cwd": "/work/demo",
                "createdAt": "2026-08-01T00:00:00.000Z",
                "updatedAt": "2026-08-01T00:00:02.000Z",
            }
        ),
        json.dumps(
            {
                "type": "message",
                "role": "user",
                "text": "Find it",
                "timestamp": "2026-08-01T00:00:00.000Z",
            }
        ),
        json.dumps(
            {
                "type": "message",
                "role": "assistant",
                "text": "Found session 019f0000-0000-7000-8000-000000000099.",
                "timestamp": "2026-08-01T00:00:02.000Z",
                "sources": ["019f0000-0000-7000-8000-000000000099"],
            }
        ),
    ]


class CmdmintThreadParserTests(unittest.TestCase):
    def test_parser_reads_cmdmint_metadata_and_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{THREAD_ID}.jsonl"
            path.write_text("\n".join(_thread_lines()) + "\n", encoding="utf-8")

            self.assertEqual(_detect_format(path), "cmdmint")
            meta = get_meta(path)
            self.assertIsNotNone(meta)
            assert meta is not None
            self.assertEqual(meta.source, "cmdmint")
            self.assertEqual(meta.uuid, THREAD_ID)
            self.assertEqual(meta.cwd, "/work/demo")
            self.assertEqual(meta.slug, "Find the MCP selector conversation")
            self.assertEqual(meta.timestamp, "2026-08-01T00:00:02.000Z")
            self.assertEqual(meta.preview, "Find it")
            self.assertEqual(
                [(turn.role, turn.text) for turn in parse_jsonl(path)],
                [
                    ("user", "Find it"),
                    ("assistant", "Found session 019f0000-0000-7000-8000-000000000099."),
                ],
            )

    def test_malformed_records_are_ignored_without_losing_valid_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{THREAD_ID}.jsonl"
            lines = _thread_lines()
            path.write_text(
                "\n".join([lines[0], "not-json", lines[1], '{"type":"message","role":"tool"}', lines[2]])
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(meta := get_meta(path), meta)
            self.assertEqual(
                [(turn.role, turn.text) for turn in parse_jsonl(path)],
                [("user", "Find it"), ("assistant", "Found session 019f0000-0000-7000-8000-000000000099.")],
            )


class CmdmintThreadScannerTests(unittest.TestCase):
    def test_scanner_uses_cmdmint_home_groups_by_cwd_and_filters_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            threads = root / "threads"
            threads.mkdir()
            thread_path = threads / f"{THREAD_ID}.jsonl"
            thread_path.write_text("\n".join(_thread_lines()) + "\n", encoding="utf-8")
            cache_path = root / "meta-cache.json"
            with patch.dict(os.environ, {"CMDMINT_HOME": str(root)}, clear=False), patch.object(
                scanner, "_CACHE_PATH", cache_path
            ):
                projects = scanner.scan_projects(source="cmdmint")

                self.assertEqual(len(projects), 1)
                self.assertEqual(projects[0].display_path, "[cmdmint] /work/demo")
                self.assertEqual([c.uuid for p in projects for c in p.conversations], [THREAD_ID])
                self.assertEqual(projects[0].conversations[0].source, "cmdmint")
                self.assertEqual(scanner._cmdmint_threads_dir(), threads)

                codex_projects = scanner.scan_projects(source="codex")
                self.assertFalse(
                    any(c.uuid == THREAD_ID for p in codex_projects for c in p.conversations)
                )

    def test_scanner_ignores_malformed_cmdmint_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            threads = root / "threads"
            threads.mkdir()
            (threads / f"{THREAD_ID}.jsonl").write_text("not-json\n", encoding="utf-8")
            with patch.dict(os.environ, {"CMDMINT_HOME": str(root)}, clear=False), patch.object(
                scanner, "_CACHE_PATH", root / "cache.json"
            ):
                projects = scanner.scan_projects(source="cmdmint")
            self.assertEqual(projects, [])


if __name__ == "__main__":
    unittest.main()
