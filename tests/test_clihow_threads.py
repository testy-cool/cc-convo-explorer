import contextlib
import inspect
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import agentconvos.app as app_module
from agentconvos import scanner
from agentconvos.app import (
    _RESUMABLE_SOURCES,
    _SOURCE_ORDER,
    _SOURCE_STYLE,
    _resume_cmd,
    main,
)
from agentconvos.parser import ConversationMeta, _detect_format, get_meta, parse_jsonl

THREAD_ID = "019f0000-0000-7000-8000-000000000001"


def _thread_lines(thread_id: str = THREAD_ID) -> list[str]:
    return [
        json.dumps(
            {
                "type": "clihow_thread",
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


class ClihowThreadParserTests(unittest.TestCase):
    def test_parser_reads_clihow_metadata_and_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / f"{THREAD_ID}.jsonl"
            path.write_text("\n".join(_thread_lines()) + "\n", encoding="utf-8")

            self.assertEqual(_detect_format(path), "clihow")
            meta = get_meta(path)
            self.assertIsNotNone(meta)
            assert meta is not None
            self.assertEqual(meta.source, "clihow")
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


class ClihowThreadScannerTests(unittest.TestCase):
    def test_scanner_uses_clihow_home_groups_by_cwd_and_filters_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            threads = root / "threads"
            threads.mkdir()
            thread_path = threads / f"{THREAD_ID}.jsonl"
            thread_path.write_text("\n".join(_thread_lines()) + "\n", encoding="utf-8")
            cache_path = root / "meta-cache.json"
            with patch.dict(os.environ, {"CLIHOW_HOME": str(root)}, clear=False), patch.object(
                scanner, "_CACHE_PATH", cache_path
            ):
                projects = scanner.scan_projects(source="clihow")

                self.assertEqual(len(projects), 1)
                self.assertEqual(projects[0].display_path, "[clihow] /work/demo")
                self.assertEqual([c.uuid for p in projects for c in p.conversations], [THREAD_ID])
                self.assertEqual(projects[0].conversations[0].source, "clihow")
                self.assertEqual(scanner._clihow_threads_dir(), threads)

                codex_projects = scanner.scan_projects(source="codex")
                self.assertFalse(
                    any(c.uuid == THREAD_ID for p in codex_projects for c in p.conversations)
                )

    def test_scanner_ignores_malformed_clihow_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            threads = root / "threads"
            threads.mkdir()
            (threads / f"{THREAD_ID}.jsonl").write_text("not-json\n", encoding="utf-8")
            with patch.dict(os.environ, {"CLIHOW_HOME": str(root)}, clear=False), patch.object(
                scanner, "_CACHE_PATH", root / "cache.json"
            ):
                projects = scanner.scan_projects(source="clihow")
            self.assertEqual(projects, [])


class ClihowThreadAppTests(unittest.TestCase):
    def test_clihow_is_a_first_class_source_and_resume_target(self):
        self.assertEqual(
            _resume_cmd("clihow", THREAD_ID),
            ["clihow", "ask", "--thread", THREAD_ID],
        )
        self.assertEqual(_SOURCE_STYLE["clihow"], ("Clihow", "bold #a78bfa"))
        self.assertIn("clihow", _SOURCE_ORDER)
        self.assertIn("clihow", _RESUMABLE_SOURCES)

        project = scanner.Project(
            "clihow:/work/demo",
            "[clihow] /work/demo",
            [],
        )
        output = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["agentconvos", "--source", "clihow", "--list", "--json"]
        try:
            with (
                patch("agentconvos.scanner.scan_projects", return_value=[project]) as scan,
                contextlib.redirect_stdout(output),
            ):
                main()
        finally:
            sys.argv = old_argv

        scan.assert_called_once()
        self.assertEqual(scan.call_args.kwargs["source"], "clihow")
        self.assertEqual(json.loads(output.getvalue())["total_conversations"], 0)

    def test_main_passes_source_and_date_filters_to_the_textual_app(self):
        observed: dict[str, object] = {}

        class FakeApp:
            _resume_meta = None
            _handoff_meta = None

            def __init__(self, **kwargs):
                observed.update(kwargs)

            def run(self):
                return None

        old_argv = sys.argv
        sys.argv = [
            "agentconvos",
            "--source",
            "clihow",
            "--after",
            "2026-07-01",
            "--before",
            "2026-08-01",
        ]
        try:
            with patch.object(app_module, "ConvoExplorer", FakeApp):
                main()
        finally:
            sys.argv = old_argv

        self.assertEqual(
            observed,
            {
                "extra_dirs": None,
                "source": "clihow",
                "after": "2026-07-01",
                "before": "2026-08-01",
            },
        )


class ClihowThreadTuiTests(unittest.IsolatedAsyncioTestCase):
    async def test_textual_app_applies_source_filter_and_plain_mode_keeps_all_sources(self):
        self.assertIn("source", inspect.signature(app_module.ConvoExplorer).parameters)

        clihow_meta = ConversationMeta(
            path=Path("/tmp/clihow-thread.jsonl"),
            uuid="019f0000-0000-7000-8000-000000000010",
            slug="clihow-thread",
            timestamp="2026-08-01T00:00:00.000Z",
            cwd="/work/demo",
            preview="Clihow result",
            source="clihow",
        )
        codex_meta = ConversationMeta(
            path=Path("/tmp/codex-thread.jsonl"),
            uuid="019f0000-0000-7000-8000-000000000011",
            slug="codex-thread",
            timestamp="2026-08-01T00:00:00.000Z",
            cwd="/work/demo",
            preview="Codex result",
            source="codex",
        )
        clihow_project = scanner.Project(
            "clihow:demo",
            "[clihow] /work/demo",
            [clihow_meta],
        )
        codex_project = scanner.Project(
            "codex:demo",
            "[codex] /work/demo",
            [codex_meta],
        )
        observed: list[dict[str, object]] = []
        sync_sources: list[set[str]] = []

        def scan(**kwargs):
            observed.append(kwargs)
            if kwargs.get("source") == "clihow":
                return [clihow_project]
            return [clihow_project, codex_project]

        class ReadyIndex:
            def search(self, _query):
                return {}

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                sync_sources.append({meta.source for meta in conversations})
                count = len(conversations)
                return SimpleNamespace(
                    total=count,
                    checked=count,
                    indexed=0,
                    unchanged=count,
                    removed=0,
                    failed=0,
                )

        async def conversation_sources(tui, pilot):
            for _ in range(40):
                await pilot.pause()
                metas = [
                    node.data.meta
                    for node in tui._walk_tree_nodes()
                    if node.data and node.data.kind == "convo" and node.data.meta
                ]
                if metas:
                    return {meta.source for meta in metas}
            return set()

        async def wait_for_sync(pilot, expected_count):
            for _ in range(40):
                if len(sync_sources) >= expected_count:
                    return
                await pilot.pause()
            self.fail(f"expected {expected_count} index syncs, got {len(sync_sources)}")

        with patch.object(app_module, "scan_projects", side_effect=scan):
            filtered = app_module.ConvoExplorer(
                source="clihow",
                after="2026-07-01",
                before="2026-08-01",
                search_index=ReadyIndex(),
            )
            async with filtered.run_test(size=(100, 32)) as pilot:
                self.assertEqual(await conversation_sources(filtered, pilot), {"clihow"})
                await wait_for_sync(pilot, 1)
                self.assertEqual(sync_sources[0], {"clihow", "codex"})

            plain = app_module.ConvoExplorer(search_index=ReadyIndex())
            async with plain.run_test(size=(100, 32)) as pilot:
                self.assertEqual(
                    await conversation_sources(plain, pilot),
                    {"clihow", "codex"},
                )
                await wait_for_sync(pilot, 2)
                self.assertEqual(sync_sources[1], {"clihow", "codex"})

        self.assertIn(
            {
                "extra_dirs": None,
                "source": "clihow",
                "after": "2026-07-01",
                "before": "2026-08-01",
            },
            observed,
        )
        self.assertIn(
            {"extra_dirs": None, "source": None, "after": None, "before": None},
            observed,
        )


if __name__ == "__main__":
    unittest.main()
