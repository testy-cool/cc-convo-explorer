import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import agentconvos.app as app_module
import agentconvos.parser as parser_module
from textual.widgets import Input, Static
from agentconvos.parser import ConversationMeta, Turn
from agentconvos.scanner import Project


def _meta(path: Path, uuid: str, timestamp: str, cwd: Path) -> ConversationMeta:
    return ConversationMeta(
        path=path,
        uuid=uuid,
        slug=f"session-{uuid[:4]}",
        timestamp=timestamp,
        cwd=str(cwd),
        preview="search preview",
        source="codex",
    )


class SearchErgonomicsTests(unittest.TestCase):
    def test_query_parser_supports_words_and_quoted_phrases(self):
        parse_terms = getattr(parser_module, "parse_search_terms", None)
        self.assertIsNotNone(parse_terms, "search query parser is missing")

        self.assertEqual(
            parse_terms('auth "request id" AUTH'),
            ["auth", "request id"],
        )

    def test_search_matches_terms_across_turns_and_ranks_exact_phrase_first(self):
        root = Path("/tmp/search-ranking")
        split_path = root / "split.jsonl"
        exact_path = root / "exact.jsonl"
        metas = {
            split_path: _meta(split_path, "split-session", "2026-07-15T12:00:00", root),
            exact_path: _meta(exact_path, "exact-session", "2026-07-14T12:00:00", root),
        }
        turns = {
            split_path: [
                Turn("user", "The authentication flow is failing."),
                Turn("assistant", "I will inspect the middleware next."),
            ],
            exact_path: [
                Turn("user", "Please inspect the auth middleware implementation."),
            ],
        }

        with (
            patch("agentconvos.parser.get_meta", side_effect=lambda path: metas[path]),
            patch("agentconvos.parser.parse_jsonl", side_effect=lambda path: turns[path]),
        ):
            hits = parser_module.search_conversations(
                [split_path, exact_path],
                "auth middleware",
            )

        self.assertGreaterEqual(len(hits), 3)
        self.assertEqual(hits[0].meta.uuid, "exact-session")
        self.assertIn("auth middleware", hits[0].snippet.lower())
        self.assertEqual(
            {hit.meta.uuid for hit in hits},
            {"split-session", "exact-session"},
        )

    def test_rich_highlight_marks_every_query_term_case_insensitively(self):
        highlight = getattr(app_module, "_highlight_matches", None)
        self.assertIsNotNone(highlight, "Rich search highlighting is missing")

        rendered = highlight("Auth middleware and AUTH logs", ["auth", "middleware"])

        self.assertEqual(rendered.plain, "Auth middleware and AUTH logs")
        highlighted_text = [rendered.plain[span.start:span.end] for span in rendered.spans]
        self.assertEqual(highlighted_text, ["Auth", "middleware", "AUTH"])

    def test_match_excerpt_centers_the_visible_text_on_the_hit(self):
        excerpt = getattr(app_module, "_matching_excerpt", None)
        self.assertIsNotNone(excerpt, "match-centered excerpts are missing")

        text = "prefix " * 30 + "AUTH MIDDLEWARE failed here" + " suffix" * 30
        result = excerpt(text, ["auth", "middleware"], width=70)

        self.assertLessEqual(len(result), 76)
        self.assertTrue(result.startswith("…"))
        self.assertTrue(result.endswith("…"))
        self.assertIn("AUTH MIDDLEWARE", result)

    def test_markdown_highlight_makes_matches_visible_in_preview(self):
        highlight = getattr(app_module, "_highlight_markdown", None)
        self.assertIsNotNone(highlight, "preview search highlighting is missing")

        self.assertEqual(
            highlight("Auth middleware failed", ["auth", "middleware"]),
            "**Auth** **middleware** failed",
        )


class FuzzyFinderTests(unittest.TestCase):
    def test_large_transcript_preview_uses_cached_context_without_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "huge.jsonl"
            path.write_text("large transcript", encoding="utf-8")
            meta = ConversationMeta(
                path=path,
                uuid="huge-session",
                slug="huge-auth-session",
                timestamp="2026-07-18T10:30:00",
                cwd=str(root),
                preview="First prompt about auth middleware",
                source="codex",
            )
            stream = io.StringIO()

            with (
                patch("agentconvos.parser.get_meta", return_value=meta),
                patch(
                    "agentconvos.summarize.load_summaries",
                    return_value={meta.uuid: "Cached authentication summary"},
                ),
                patch(
                    "agentconvos.app.parse_jsonl",
                    side_effect=AssertionError("large preview must stay lazy"),
                ),
                contextlib.redirect_stdout(stream),
            ):
                app_module._print_fuzzy_preview(path, max_parse_bytes=1)

        output = stream.getvalue()
        self.assertIn("Cached authentication summary", output)
        self.assertIn("First prompt about auth middleware", output)
        self.assertIn("Large transcript", output)

    def test_fuzzy_picker_searches_cached_metadata_and_previews_lazily(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = ConversationMeta(
                path=path,
                uuid="019f1234-abcd-7000-8000-123456789abc",
                slug="fix-auth-middleware",
                timestamp="2026-07-18T10:30:00",
                cwd=str(root / "checkout"),
                preview="Investigate dropped request IDs",
                source="codex",
                git_branch="fix/request-id",
            )
            captured = {}

            def fake_runner(command, **kwargs):
                captured["command"] = command
                captured["input"] = kwargs["input"]
                selected_row = kwargs["input"].splitlines()[0]
                return SimpleNamespace(returncode=0, stdout=selected_row + "\n")

            with (
                patch(
                    "agentconvos.summarize.load_summaries",
                    return_value={meta.uuid: "Authentication debugging notes"},
                ),
                patch(
                    "agentconvos.app.parse_jsonl",
                    side_effect=AssertionError("picker must not preload transcripts"),
                ),
            ):
                selected = app_module._pick_conversation_fuzzy(
                    [meta],
                    initial_query="auth reqid",
                    fzf_path="/usr/bin/fzf",
                    runner=fake_runner,
                )

        self.assertEqual(selected, meta)
        self.assertIn("fix-auth-middleware", captured["input"])
        self.assertIn("Investigate dropped request IDs", captured["input"])
        self.assertIn("Authentication debugging notes", captured["input"])
        self.assertIn("fix/request-id", captured["input"])
        self.assertIn("--nth=2..7", captured["command"])
        self.assertIn("--with-nth=2..6", captured["command"])
        self.assertIn("--query=auth reqid", captured["command"])
        preview_arg = next(
            arg for arg in captured["command"] if arg.startswith("--preview=")
        )
        self.assertIn("agentconvos.app --peek {8}", preview_arg)

    def test_find_flag_selects_without_starting_the_textual_tui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "selected-session", "2026-07-18T10:30:00", root)
            project = Project("tmp", str(root), [meta])
            stream = io.StringIO()
            old_argv = sys.argv
            sys.argv = ["agentconvos", "--find", "auth reqid"]
            try:
                with (
                    patch("agentconvos.scanner.scan_projects", return_value=[project]),
                    patch(
                        "agentconvos.app._pick_conversation_fuzzy",
                        return_value=meta,
                    ) as picker,
                    patch(
                        "agentconvos.app.ConvoExplorer.run",
                        side_effect=AssertionError("--find must not start Textual"),
                    ),
                    contextlib.redirect_stdout(stream),
                    contextlib.redirect_stderr(stream),
                ):
                    app_module.main()
            finally:
                sys.argv = old_argv

        picker.assert_called_once_with([meta], initial_query="auth reqid")
        output = stream.getvalue()
        self.assertIn(meta.uuid, output)
        self.assertIn(f"agentconvos --show {meta.uuid}", output)
        self.assertIn(f"agentconvos --resume {meta.uuid}", output)

    def test_direct_preview_path_accepts_non_jsonl_conversation_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agy-conversation.db"
            path.write_bytes(b"")

            with patch(
                "agentconvos.scanner.resolve_ids",
                side_effect=AssertionError("direct paths must not trigger a full rescan"),
            ):
                resolved = app_module._resolve_args([str(path)])

        self.assertEqual(resolved, [path])


class ResumeErgonomicsTests(unittest.TestCase):
    def test_bare_resume_selects_latest_session_for_current_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            older_path = cwd / "older.jsonl"
            newer_path = cwd / "newer.jsonl"
            older_path.write_text("", encoding="utf-8")
            newer_path.write_text("", encoding="utf-8")
            older = _meta(older_path, "older-session", "2026-07-14T10:00:00", cwd)
            newer = _meta(newer_path, "newer-session", "2026-07-15T10:00:00", cwd)
            project = Project("tmp", str(cwd), [older, newer])

            old_argv = sys.argv
            old_cwd = os.getcwd()
            sys.argv = ["agentconvos", "--resume", "--dry-run"]
            stream = io.StringIO()
            try:
                os.chdir(cwd)
                with (
                    patch("agentconvos.scanner.scan_projects", return_value=[project]),
                    contextlib.redirect_stdout(stream),
                    contextlib.redirect_stderr(stream),
                ):
                    try:
                        app_module.main()
                    except SystemExit as exc:
                        self.fail(f"bare --resume should be accepted, exited with {exc.code}")
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)

        output = stream.getvalue()
        self.assertIn("Resuming: session-newe", output)
        self.assertIn("newer-session", output)
        self.assertNotIn("older-session", output)

    def test_resume_confirmation_includes_agent_cwd_full_id_and_command(self):
        describe = getattr(app_module, "_resume_description", None)
        self.assertIsNotNone(describe, "resume confirmation details are missing")

        meta = ConversationMeta(
            path=Path("/tmp/project/session.jsonl"),
            uuid="019f1234-abcd-7000-8000-123456789abc",
            slug="useful-session",
            timestamp="2026-07-15T14:30:00",
            cwd="/tmp/project",
            preview="",
            source="codex",
        )
        description = describe(meta)

        self.assertIn("Codex", description)
        self.assertIn("/tmp/project", description)
        self.assertIn(meta.uuid, description)
        self.assertIn("codex resume", description)


class TuiErgonomicsTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_enter_opens_first_match_with_highlighted_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "search-session", "2026-07-15T14:30:00", cwd)
            project = Project("tmp", str(cwd), [meta])
            turns = [
                Turn("user", "Please inspect the auth middleware failure."),
                Turn("assistant", "The auth middleware drops the request id."),
            ]

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch("agentconvos.app.parse_jsonl", return_value=turns),
            ):
                tui = app_module.ConvoExplorer()
                async with tui.run_test(size=(110, 36)) as pilot:
                    await pilot.pause()
                    search = tui.query_one("#filter-input", Input)
                    search.focus()
                    search.value = "auth middleware"
                    await pilot.pause()

                    result_nodes = [
                        node
                        for node in tui._walk_tree_nodes()
                        if node.data and node.data.kind == "convo"
                    ]
                    self.assertEqual(len(result_nodes), 1)
                    self.assertGreaterEqual(len(result_nodes[0].label.spans), 2)

                    await pilot.press("enter")
                    await pilot.pause()

                    self.assertEqual(tui.current_meta, meta)
                    title = str(tui.query_one("#right-title", Static).render())
                    self.assertEqual(title, "MATCHES (2 turns) · R RESUME")

    async def test_escape_clears_search_from_the_search_box(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "search-session", "2026-07-15T14:30:00", cwd)
            project = Project("tmp", str(cwd), [meta])

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch("agentconvos.app.parse_jsonl", return_value=[Turn("user", "auth")]),
            ):
                tui = app_module.ConvoExplorer()
                async with tui.run_test(size=(100, 32)) as pilot:
                    await pilot.pause()
                    search = tui.query_one("#filter-input", Input)
                    search.focus()
                    search.value = "auth"
                    await pilot.pause()

                    await pilot.press("escape")
                    await pilot.pause()

                    self.assertEqual(search.value, "")

    async def test_escape_dismisses_resume_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "resume-session", "2026-07-15T14:30:00", cwd)
            project = Project("tmp", str(cwd), [meta])

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch(
                    "agentconvos.app.parse_jsonl",
                    return_value=[Turn("user", "searchable conversation")],
                ),
            ):
                tui = app_module.ConvoExplorer()
                async with tui.run_test(size=(100, 32)) as pilot:
                    await pilot.pause()
                    tui.current_meta = meta
                    tui.action_resume()
                    await pilot.pause()
                    self.assertIsInstance(tui.screen, app_module.ResumeScreen)

                    await pilot.press("escape")
                    await pilot.pause()

                    self.assertNotIsInstance(tui.screen, app_module.ResumeScreen)


if __name__ == "__main__":
    unittest.main()
