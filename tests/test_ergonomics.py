import contextlib
import io
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from textual.widgets import Input, Static

import agentconvos.app as app_module
import agentconvos.parser as parser_module
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
    def test_navigation_timestamps_stay_compact(self):
        formatter = getattr(app_module, "_fmt_nav_ts", None)
        self.assertIsNotNone(formatter, "compact navigation timestamps are missing")
        self.assertEqual(formatter("2026-07-18T12:23:45"), "07-18 12:23")

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
    def test_bare_resume_accepts_latest_pi_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            session_path = cwd / "pi-session.jsonl"
            session_path.write_text("", encoding="utf-8")
            meta = ConversationMeta(
                path=session_path,
                uuid="pi-session",
                slug="session-pi",
                timestamp="2026-07-15T10:00:00",
                cwd=str(cwd),
                preview="Pi session",
                source="pi",
            )
            project = Project("pi:tmp", f"[pi] {cwd}", [meta])

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
                    app_module.main()
            finally:
                sys.argv = old_argv
                os.chdir(old_cwd)

        output = stream.getvalue()
        self.assertIn("pi --session pi-session", output)

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
    async def test_status_rail_sits_above_the_footer_on_small_terminals(self):
        class ReadyIndex:
            def search(self, _query):
                return {}

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                return SimpleNamespace(
                    total=len(conversations),
                    checked=len(conversations),
                    indexed=0,
                    unchanged=len(conversations),
                    removed=0,
                    failed=0,
                )

        with patch("agentconvos.app.scan_projects", return_value=[]):
            tui = app_module.ConvoExplorer(search_index=ReadyIndex())
            async with tui.run_test(size=(80, 24)) as pilot:
                await pilot.pause()

                status_rail = tui.query_one("#status-rail")
                footer = tui.query_one("Footer")
                left_title = tui.query_one("#left-title")
                search = tui.query_one("#filter-input", Input)
                self.assertLess(status_rail.region.bottom, footer.region.bottom)
                self.assertEqual(status_rail.region.bottom, footer.region.y)
                self.assertLessEqual(left_title.region.bottom, search.region.y)

    async def test_projects_render_before_background_index_completes(self):
        class BlockingIndex:
            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()

            def search(self, _query):
                return {}

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                self.started.set()
                self.release.wait(timeout=3)
                return SimpleNamespace(
                    total=len(conversations),
                    checked=len(conversations),
                    indexed=len(conversations),
                    unchanged=0,
                    removed=0,
                    failed=0,
                )

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "instant-session", "2026-07-18T10:30:00", cwd)
            project = Project("tmp", str(cwd), [meta])
            index = BlockingIndex()

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch("agentconvos.app.parse_jsonl") as parse_transcript,
            ):
                tui = app_module.ConvoExplorer(search_index=index)
                async with tui.run_test(size=(110, 36)) as pilot:
                    try:
                        for _ in range(20):
                            await pilot.pause()
                            result_nodes = [
                                node
                                for node in tui._walk_tree_nodes()
                                if node.data and node.data.kind == "convo"
                            ]
                            if result_nodes and index.started.is_set():
                                break

                        self.assertEqual(len(result_nodes), 1)
                        self.assertTrue(index.started.is_set())
                        self.assertFalse(index.release.is_set())
                        parse_transcript.assert_not_called()
                        index_label = str(
                            tui.query_one("#index-status", Static).render()
                        )
                        self.assertIn("INDEXING", index_label)
                    finally:
                        index.release.set()

    async def test_search_uses_persisted_snippets_without_preloading_transcripts(self):
        class ReadyIndex:
            def __init__(self, uuid):
                self.uuid = uuid

            def search(self, query):
                if query == "auth middleware":
                    return {self.uuid: "The auth middleware drops request IDs"}
                return {}

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                return SimpleNamespace(
                    total=len(conversations),
                    checked=len(conversations),
                    indexed=0,
                    unchanged=len(conversations),
                    removed=0,
                    failed=0,
                )

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "indexed-session", "2026-07-18T10:30:00", cwd)
            meta.preview = "Unrelated first prompt"
            project = Project("tmp", str(cwd), [meta])
            index = ReadyIndex(meta.uuid)

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch("agentconvos.app.parse_jsonl") as parse_transcript,
            ):
                tui = app_module.ConvoExplorer(search_index=index)
                async with tui.run_test(size=(110, 36)) as pilot:
                    await pilot.pause()
                    search = tui.query_one("#filter-input", Input)
                    search.value = "auth middleware"
                    for _ in range(30):
                        await pilot.pause(0.03)
                        result_nodes = [
                            node
                            for node in tui._walk_tree_nodes()
                            if node.data and node.data.kind == "convo"
                        ]
                        if result_nodes and "drops request IDs" in result_nodes[0].label.plain:
                            break

                    result_nodes = [
                        node
                        for node in tui._walk_tree_nodes()
                        if node.data and node.data.kind == "convo"
                    ]
                    self.assertEqual(len(result_nodes), 1)
                    self.assertIn("drops request IDs", result_nodes[0].label.plain)
                    parse_transcript.assert_not_called()

    async def test_filter_input_debounces_intermediate_queries(self):
        class RecordingIndex:
            def __init__(self):
                self.queries = []

            def search(self, query):
                self.queries.append(query)
                return {}

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                return SimpleNamespace(
                    total=len(conversations),
                    checked=len(conversations),
                    indexed=0,
                    unchanged=len(conversations),
                    removed=0,
                    failed=0,
                )

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "debounce-session", "2026-07-18T10:30:00", cwd)
            project = Project("tmp", str(cwd), [meta])
            index = RecordingIndex()

            with patch("agentconvos.app.scan_projects", return_value=[project]):
                tui = app_module.ConvoExplorer(search_index=index)
                async with tui.run_test(size=(110, 36)) as pilot:
                    for _ in range(20):
                        await pilot.pause()
                        if "INDEX READY" in str(
                            tui.query_one("#index-status", Static).render()
                        ):
                            break

                    index.queries.clear()
                    search = tui.query_one("#filter-input", Input)
                    search.value = "a"
                    await pilot.pause(0.03)
                    search.value = "ag"
                    await pilot.pause(0.03)
                    search.value = "agentconvos"
                    await pilot.pause(0.03)

                    self.assertEqual(index.queries, [])

                    await pilot.pause(0.25)
                    for _ in range(20):
                        await pilot.pause()
                        if index.queries:
                            break

                    self.assertEqual(index.queries, ["agentconvos"])

    async def test_stale_filter_result_is_discarded_before_tree_mutation(self):
        with patch("agentconvos.app.scan_projects", return_value=[]):
            tui = app_module.ConvoExplorer()
            async with tui.run_test(size=(100, 32)):
                tui._filter_query = "agentconvos"
                tui._filter_generation = 2
                stale_result = SimpleNamespace(
                    projects=[],
                    indexed_matches={},
                    filtered_count=0,
                )

                with (
                    patch.object(tui, "_populate_tree") as populate_tree,
                    patch.object(tui, "_show_search_summary") as show_summary,
                ):
                    tui._filter_finished("a", 1, stale_result)

                populate_tree.assert_not_called()
                show_summary.assert_not_called()

    async def test_preview_header_shortens_the_home_directory(self):
        """The tree groups paths under ~, so the preview should agree instead
        of printing the whole absolute path."""
        shorten = getattr(app_module, "_short_path", None)
        self.assertIsNotNone(shorten, "path shortening helper is missing")
        self.assertEqual(shorten("/srv/elsewhere"), "/srv/elsewhere")

        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cwd = home / "work" / "billing-api"
            cwd.mkdir(parents=True)
            meta = _meta(cwd / "s.jsonl", "preview-home", "2026-07-18T10:30:00", cwd)
            turns = [Turn("user", "hello"), Turn("assistant", "hi")]
            captured: list[str] = []

            with patch("agentconvos.app.scan_projects", return_value=[]):
                tui = app_module.ConvoExplorer()
                async with tui.run_test(size=(100, 32)) as pilot:
                    with (
                        patch("agentconvos.app.parse_jsonl", return_value=turns),
                        patch("pathlib.Path.home", return_value=home),
                        patch.object(
                            tui, "_set_preview",
                            side_effect=lambda md, *a, **k: captured.append(md),
                        ),
                    ):
                        tui.request_preview(meta)
                        for _ in range(60):
                            await pilot.pause(0.05)
                            if captured:
                                break

            self.assertTrue(captured, "preview was never rendered")
            self.assertIn("**CWD:** ~/work/billing-api", captured[0])
            self.assertNotIn(str(cwd), captured[0])

    async def test_late_index_callbacks_after_shutdown_are_ignored(self):
        """A slow index sync can finish after the app exits; its UI callbacks
        must not crash on the already-removed status widgets."""
        with patch("agentconvos.app.scan_projects", return_value=[]):
            tui = app_module.ConvoExplorer()
            async with tui.run_test(size=(100, 32)):
                pass

            stats = SimpleNamespace(total=5, checked=5, failed=0)
            tui._set_index_progress(stats)
            tui._index_finished(stats)
            tui._index_failed("boom")

    async def test_broad_filter_is_bounded_and_applied_in_one_batch(self):
        class BroadIndex:
            def search(self, query):
                if query != "a":
                    return {}
                return {meta.uuid: "a broad match" for meta in metas}

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                return SimpleNamespace(
                    total=len(conversations),
                    checked=len(conversations),
                    indexed=0,
                    unchanged=len(conversations),
                    removed=0,
                    failed=0,
                )

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            metas = [
                _meta(
                    cwd / f"session-{index}.jsonl",
                    f"broad-session-{index}",
                    "2026-07-18T10:30:00",
                    cwd,
                )
                for index in range(225)
            ]
            project = Project("tmp", str(cwd), metas)

            with patch("agentconvos.app.scan_projects", return_value=[project]):
                tui = app_module.ConvoExplorer(search_index=BroadIndex())
                with patch.object(tui, "batch_update", wraps=tui.batch_update) as batch_update:
                    async with tui.run_test(size=(110, 36)) as pilot:
                        await pilot.pause()
                        search = tui.query_one("#filter-input", Input)
                        search.value = "a"
                        for _ in range(40):
                            await pilot.pause(0.03)
                            result_nodes = [
                                node
                                for node in tui._walk_tree_nodes()
                                if node.data and node.data.kind == "convo"
                            ]
                            if result_nodes and "RESULTS" in str(
                                tui.query_one("#left-title", Static).render()
                            ):
                                break

                        self.assertEqual(len(result_nodes), 200)

                    self.assertGreaterEqual(batch_update.call_count, 2)

    async def test_preview_shows_loading_state_while_transcript_parses(self):
        class ReadyIndex:
            def search(self, _query):
                return {}

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                return SimpleNamespace(
                    total=len(conversations),
                    checked=len(conversations),
                    indexed=0,
                    unchanged=len(conversations),
                    removed=0,
                    failed=0,
                )

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "preview-session", "2026-07-18T10:30:00", cwd)
            project = Project("tmp", str(cwd), [meta])
            parse_started = threading.Event()
            release_parse = threading.Event()

            def slow_parse(_path):
                parse_started.set()
                release_parse.wait(timeout=3)
                return [Turn("assistant", "Loaded preview")]

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch("agentconvos.app.parse_jsonl", side_effect=slow_parse),
            ):
                tui = app_module.ConvoExplorer(search_index=ReadyIndex())
                async with tui.run_test(size=(110, 36)) as pilot:
                    try:
                        await pilot.pause()
                        tui.request_preview(meta)
                        for _ in range(20):
                            await pilot.pause()
                            if parse_started.is_set():
                                break

                        preview_scroll = tui.query_one("#preview-scroll")
                        self.assertTrue(parse_started.is_set())
                        self.assertTrue(preview_scroll.loading)

                        release_parse.set()
                        for _ in range(20):
                            await pilot.pause()
                            if not preview_scroll.loading:
                                break
                        self.assertFalse(preview_scroll.loading)
                    finally:
                        release_parse.set()

    async def test_cancelled_preview_cannot_overwrite_the_latest_conversation(self):
        class ReadyIndex:
            def search(self, _query):
                return {}

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                return SimpleNamespace(
                    total=len(conversations),
                    checked=len(conversations),
                    indexed=0,
                    unchanged=len(conversations),
                    removed=0,
                    failed=0,
                )

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            first_path = cwd / "first.jsonl"
            second_path = cwd / "second.jsonl"
            first_path.write_text("", encoding="utf-8")
            second_path.write_text("", encoding="utf-8")
            first = _meta(first_path, "first-preview", "2026-07-18T10:30:00", cwd)
            second = _meta(second_path, "second-preview", "2026-07-18T10:31:00", cwd)
            project = Project("tmp", str(cwd), [second, first])
            first_started = threading.Event()
            release_first = threading.Event()

            def parse_preview(path):
                if path == first_path:
                    first_started.set()
                    release_first.wait(timeout=3)
                    return [Turn("user", "First"), Turn("assistant", "First result")]
                return [Turn("assistant", "Second result")]

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch("agentconvos.app.parse_jsonl", side_effect=parse_preview),
            ):
                tui = app_module.ConvoExplorer(search_index=ReadyIndex())
                async with tui.run_test(size=(110, 36)) as pilot:
                    try:
                        await pilot.pause()
                        tui.request_preview(first)
                        for _ in range(20):
                            await pilot.pause()
                            if first_started.is_set():
                                break

                        tui.request_preview(second)
                        for _ in range(20):
                            await pilot.pause()
                            if "1 turns" in str(
                                tui.query_one("#right-title", Static).render()
                            ):
                                break

                        release_first.set()
                        for _ in range(20):
                            await pilot.pause()

                        title = str(tui.query_one("#right-title", Static).render())
                        self.assertEqual(title, "CONVERSATION · 1 turns")
                    finally:
                        release_first.set()

    async def test_active_search_refreshes_as_background_index_makes_progress(self):
        class ProgressiveIndex:
            def __init__(self, uuid):
                self.uuid = uuid
                self.indexed = False
                self.started = threading.Event()
                self.advance = threading.Event()
                self.progress_sent = threading.Event()
                self.finish = threading.Event()

            def search(self, query):
                if self.indexed and query == "auth middleware":
                    return {self.uuid: "auth middleware indexed in the background"}
                return {}

            def sync(self, conversations, on_progress, **_kwargs):
                conversations = list(conversations)
                self.started.set()
                self.advance.wait(timeout=3)
                self.indexed = True
                progress = SimpleNamespace(
                    total=2,
                    checked=1,
                    indexed=1,
                    unchanged=0,
                    removed=0,
                    failed=0,
                )
                on_progress(progress)
                self.progress_sent.set()
                self.finish.wait(timeout=3)
                return SimpleNamespace(
                    total=2,
                    checked=2,
                    indexed=2,
                    unchanged=0,
                    removed=0,
                    failed=0,
                )

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "progress-session", "2026-07-18T10:30:00", cwd)
            meta.preview = "Unrelated prompt"
            project = Project("tmp", str(cwd), [meta])
            index = ProgressiveIndex(meta.uuid)

            with patch("agentconvos.app.scan_projects", return_value=[project]):
                tui = app_module.ConvoExplorer(search_index=index)
                async with tui.run_test(size=(110, 36)) as pilot:
                    try:
                        for _ in range(20):
                            await pilot.pause()
                            if index.started.is_set():
                                break
                        search = tui.query_one("#filter-input", Input)
                        search.value = "auth middleware"
                        for _ in range(30):
                            await pilot.pause(0.03)
                            result_nodes = [
                                node
                                for node in tui._walk_tree_nodes()
                                if node.data and node.data.kind == "convo"
                            ]
                            if not any(
                                node.data and node.data.kind == "convo"
                                for node in tui._walk_tree_nodes()
                            ):
                                break
                        self.assertFalse(
                            any(
                                node.data and node.data.kind == "convo"
                                for node in tui._walk_tree_nodes()
                            )
                        )

                        index.advance.set()
                        for _ in range(30):
                            await pilot.pause()
                            result_nodes = [
                                node
                                for node in tui._walk_tree_nodes()
                                if node.data and node.data.kind == "convo"
                            ]
                            if index.progress_sent.is_set() and result_nodes:
                                break

                        self.assertTrue(index.progress_sent.is_set())
                        self.assertEqual(len(result_nodes), 1)
                        self.assertFalse(index.finish.is_set())
                        search_title = str(
                            tui.query_one("#right-title", Static).render()
                        )
                        self.assertEqual(search_title, "SEARCH · 1")
                    finally:
                        index.advance.set()
                        index.finish.set()

    async def test_index_progress_does_not_replace_an_open_search_preview(self):
        class ReadyIndex:
            def __init__(self, uuid):
                self.uuid = uuid

            def search(self, query):
                return (
                    {self.uuid: "auth middleware indexed in the background"}
                    if query == "auth middleware"
                    else {}
                )

            def sync(self, conversations, **_kwargs):
                conversations = list(conversations)
                return SimpleNamespace(
                    total=len(conversations),
                    checked=len(conversations),
                    indexed=0,
                    unchanged=len(conversations),
                    removed=0,
                    failed=0,
                )

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            path = cwd / "session.jsonl"
            path.write_text("", encoding="utf-8")
            meta = _meta(path, "stable-preview", "2026-07-18T10:30:00", cwd)
            project = Project("tmp", str(cwd), [meta])
            turns = [
                Turn("user", "Inspect the auth middleware"),
                Turn("assistant", "The auth middleware is ready"),
            ]

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch("agentconvos.app.parse_jsonl", return_value=turns),
            ):
                tui = app_module.ConvoExplorer(search_index=ReadyIndex(meta.uuid))
                async with tui.run_test(size=(110, 36)) as pilot:
                    await pilot.pause()
                    search = tui.query_one("#filter-input", Input)
                    search.value = "auth middleware"
                    await pilot.press("enter")
                    for _ in range(20):
                        await pilot.pause()
                        if "MATCHES" in str(
                            tui.query_one("#right-title", Static).render()
                        ):
                            break

                    tui._indexing = True
                    tui._set_index_progress(
                        SimpleNamespace(
                            total=2,
                            checked=1,
                            indexed=1,
                            unchanged=0,
                            removed=0,
                            failed=0,
                        )
                    )

                    title = str(tui.query_one("#right-title", Static).render())
                    self.assertEqual(title, "MATCHES (2 turns) · R RESUME")

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
            from agentconvos.search_index import ConversationSearchIndex

            index = ConversationSearchIndex(cwd / "search.sqlite3")
            index.sync([meta], parse_conversation=lambda _path: turns)

            with (
                patch("agentconvos.app.scan_projects", return_value=[project]),
                patch("agentconvos.app.parse_jsonl", return_value=turns),
            ):
                tui = app_module.ConvoExplorer(search_index=index)
                async with tui.run_test(size=(110, 36)) as pilot:
                    await pilot.pause()
                    search = tui.query_one("#filter-input", Input)
                    search.focus()
                    search.value = "auth middleware"
                    for _ in range(30):
                        await pilot.pause(0.03)
                        result_nodes = [
                            node
                            for node in tui._walk_tree_nodes()
                            if node.data and node.data.kind == "convo"
                        ]
                        if result_nodes and "RESULTS" in str(
                            tui.query_one("#left-title", Static).render()
                        ):
                            break

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
                from agentconvos.search_index import ConversationSearchIndex

                tui = app_module.ConvoExplorer(
                    search_index=ConversationSearchIndex(cwd / "search.sqlite3")
                )
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
                from agentconvos.search_index import ConversationSearchIndex

                tui = app_module.ConvoExplorer(
                    search_index=ConversationSearchIndex(cwd / "search.sqlite3")
                )
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
