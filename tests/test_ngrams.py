import contextlib
import importlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import agentconvos.scanner as scanner_module
from agentconvos.app import main
from agentconvos.parser import ConversationMeta
from agentconvos.scanner import Project
from agentconvos.search_index import ConversationSearchIndex


def _ngrams_module():
    try:
        return importlib.import_module("agentconvos.ngrams")
    except ModuleNotFoundError:
        raise AssertionError("agentconvos.ngrams is not implemented") from None


def _meta(path: Path, source: str, uuid: str) -> ConversationMeta:
    return ConversationMeta(
        path=path,
        uuid=uuid,
        slug="",
        timestamp="2026-08-20T12:00:00Z",
        cwd="/work/project",
        preview="fixture prompt",
        source=source,
    )


def _write_claude(path: Path, assistant_text: str) -> None:
    records = [
        {
            "type": "user",
            "message": {"content": "prompt-only load-bearing"},
        },
        {
            "type": "system",
            "message": {"content": "bootstrap-only"},
        },
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "thinking", "thinking": "reasoning-only"},
                    {
                        "type": "tool_use",
                        "id": "tool-1",
                        "name": "Read",
                        "input": {"file_path": "/payload-only.py"},
                    },
                    {"type": "text", "text": assistant_text},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": "result-only",
                    }
                ]
            },
        },
    ]
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def _fixture_projects(root: Path) -> list[Project]:
    target = []
    for index in range(2):
        path = root / f"claude-{index}.jsonl"
        _write_claude(path, "The load-bearing boundary is deliberate. Load-bearing choices matter.")
        target.append(_meta(path, "claude", f"claude-{index}"))

    baseline_path = root / "codex.jsonl"
    baseline_path.write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "codex-1",
                        "timestamp": "2026-08-20T12:00:00Z",
                        "cwd": "/work/project",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "agent_message",
                        "message": "The boundary is deliberate and the implementation is complete.",
                    },
                },
            )
        ),
        encoding="utf-8",
    )
    baseline = _meta(baseline_path, "codex", "codex-1")
    return [
        Project("claude", "/work/project", target),
        Project("codex", "[codex] /work/project", [baseline]),
    ]


class NgramCliContractTests(unittest.TestCase):
    def test_help_advertises_ngram_discovery(self):
        stream = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["agentconvos", "--help"]
        try:
            with contextlib.redirect_stdout(stream):
                with self.assertRaises(SystemExit) as raised:
                    main()
        finally:
            sys.argv = old_argv

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("--ngrams", stream.getvalue())

    def test_ngrams_requires_exactly_one_source(self):
        for argv in (
            ["agentconvos", "--ngrams"],
            ["agentconvos", "--ngrams", "--source", "claude", "--source", "codex"],
        ):
            with self.subTest(argv=argv):
                stream = io.StringIO()
                old_argv = sys.argv
                sys.argv = argv
                try:
                    with contextlib.redirect_stderr(stream):
                        with self.assertRaises(SystemExit) as raised:
                            main()
                finally:
                    sys.argv = old_argv

                self.assertEqual(raised.exception.code, 2)
                self.assertIn(
                    "--ngrams requires exactly one --source",
                    stream.getvalue(),
                )

    def test_json_reports_counts_sessions_and_distinctiveness(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects = _fixture_projects(Path(tmp))
            stream = io.StringIO()
            old_argv = sys.argv
            sys.argv = [
                "agentconvos",
                "--ngrams",
                "--source",
                "claude",
                "--limit",
                "5",
                "--json",
            ]
            try:
                with (
                    patch.object(scanner_module, "scan_projects", return_value=projects),
                    patch("agentconvos.app.ConvoExplorer.run", return_value=None),
                    contextlib.redirect_stdout(stream),
                ):
                    main()
            finally:
                sys.argv = old_argv

        payload = json.loads(stream.getvalue())
        self.assertEqual(payload["source"], "claude")
        self.assertEqual(payload["comparison_baseline"], "all other indexed agent sources")
        self.assertEqual(payload["target_sessions"], 2)
        self.assertEqual(payload["baseline_sessions"], 1)
        load_bearing = next(row for row in payload["phrases"] if row["phrase"] == "load-bearing")
        self.assertEqual(load_bearing["occurrences"], 4)
        self.assertEqual(load_bearing["sessions"], 2)
        self.assertGreater(load_bearing["distinctiveness"], 1)
        self.assertIn("more prevalent", load_bearing["distinctiveness_label"])

    def test_human_output_has_comprehensible_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects = _fixture_projects(Path(tmp))
            stream = io.StringIO()
            old_argv = sys.argv
            sys.argv = ["agentconvos", "--ngrams", "--source", "claude", "--limit", "3"]
            try:
                with (
                    patch.object(scanner_module, "scan_projects", return_value=projects),
                    patch("agentconvos.app.ConvoExplorer.run", return_value=None),
                    contextlib.redirect_stdout(stream),
                ):
                    main()
            finally:
                sys.argv = old_argv

        output = stream.getvalue()
        self.assertIn("Phrase", output)
        self.assertIn("Occurrences", output)
        self.assertIn("Sessions", output)
        self.assertIn("Distinctiveness", output)
        self.assertIn("load-bearing", output)


class NgramAnalysisTests(unittest.TestCase):
    def test_tokenization_preserves_hyphens_and_rejects_code_urls_and_identifiers(self):
        phrases = _ngrams_module().phrases

        found = phrases(
            "A load-bearing choice. https://example.com/a `/tmp/foo.py` "
            "user_id deadbeef123456 abc123.\n```python\ndef helper_name(): pass\n```"
        )

        self.assertIn("load-bearing", found)
        self.assertIn("load-bearing choice", found)
        for unwanted in ("https", "example", "tmp", "foo", "user_id", "deadbeef123456", "abc123", "helper_name"):
            self.assertNotIn(unwanted, found)
        self.assertNotIn("i'll start", phrases("I'll start by checking it."))

    def test_assistant_reply_text_excludes_every_non_reply_channel(self):
        assistant_reply_text = _ngrams_module().assistant_reply_text

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claude.jsonl"
            _write_claude(path, "A load-bearing boundary.")

            text = assistant_reply_text(path)

        self.assertEqual(text, "A load-bearing boundary.")
        for excluded in (
            "prompt-only",
            "bootstrap-only",
            "payload-only",
            "result-only",
            "reasoning-only",
        ):
            self.assertNotIn(excluded, text)

    def test_ranking_favors_cross_session_characteristic_phrases(self):
        rank_phrases = _ngrams_module().rank_phrases

        target = [
            "A load-bearing boundary supports the implementation.",
            "This load-bearing choice supports the implementation.",
            "Another load-bearing decision supports the implementation.",
        ]
        baseline = [
            "The implementation is complete.",
            "This implementation is verified.",
            "Review the implementation now.",
        ]

        ranked = rank_phrases(target, baseline, limit=20)
        phrases_by_rank = [row.phrase for row in ranked]

        self.assertIn("load-bearing", phrases_by_rank)
        self.assertNotIn("the", phrases_by_rank)
        self.assertLess(
            phrases_by_rank.index("load-bearing"),
            phrases_by_rank.index("implementation") if "implementation" in phrases_by_rank else 999,
        )

    def test_index_reader_returns_assistant_turns_only(self):
        assistant_replies_from_index = _ngrams_module().assistant_replies_from_index
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript = root / "claude.jsonl"
            _write_claude(transcript, "The indexed load-bearing reply.")
            meta = _meta(transcript, "claude", "claude-indexed")
            index = ConversationSearchIndex(root / "search.sqlite3")
            index.sync([meta])

            replies = assistant_replies_from_index(index.path, [meta])

        self.assertEqual(replies[str(transcript)], "The indexed load-bearing reply.")
        self.assertNotIn("prompt-only", replies[str(transcript)])

    def test_readme_explains_scope_baseline_and_inference_limit(self):
        readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")

        self.assertIn("agentconvos --ngrams --source claude", readme)
        self.assertIn("assistant reply text only", readme)
        self.assertIn("all other indexed agent sources", readme)
        self.assertRegex(
            readme,
            r"not proof of\s+training or an agent's underlying style",
        )


if __name__ == "__main__":
    unittest.main()
