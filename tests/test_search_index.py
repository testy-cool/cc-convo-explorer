import tempfile
import unittest
from pathlib import Path

from agentconvos.parser import ConversationMeta, Turn


def _meta(path: Path, uuid: str = "session-one") -> ConversationMeta:
    return ConversationMeta(
        path=path,
        uuid=uuid,
        slug="fix-auth-middleware",
        timestamp="2026-07-18T10:30:00",
        cwd=str(path.parent),
        preview="Investigate request IDs",
        source="codex",
        git_branch="fix/request-id",
    )


class ConversationSearchIndexTests(unittest.TestCase):
    def test_sync_reuses_unchanged_rows_and_returns_prefix_matches(self):
        from agentconvos.search_index import ConversationSearchIndex

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript = root / "session.jsonl"
            transcript.write_text("first version", encoding="utf-8")
            meta = _meta(transcript)
            parse_calls = []

            def parse_conversation(path: Path):
                parse_calls.append(path)
                return [Turn("user", "The auth middleware drops request IDs")]

            index = ConversationSearchIndex(root / "search.sqlite3")
            first = index.sync([meta], parse_conversation=parse_conversation)
            second = index.sync([meta], parse_conversation=parse_conversation)
            matches = index.search("auth midd")

        self.assertEqual(first.indexed, 1)
        self.assertEqual(second.unchanged, 1)
        self.assertEqual(parse_calls, [transcript])
        self.assertIn(meta.uuid, matches)
        self.assertIn("auth middleware", matches[meta.uuid].casefold())

    def test_sync_removes_conversations_missing_from_the_latest_scan(self):
        from agentconvos.search_index import ConversationSearchIndex

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first_path = root / "first.jsonl"
            second_path = root / "second.jsonl"
            first_path.write_text("first", encoding="utf-8")
            second_path.write_text("second", encoding="utf-8")
            first = _meta(first_path, "first-session")
            second = _meta(second_path, "second-session")
            index = ConversationSearchIndex(root / "search.sqlite3")

            def parse_conversation(path: Path):
                return [Turn("user", f"unique text from {path.stem}")]

            index.sync(
                [first, second],
                parse_conversation=parse_conversation,
            )
            result = index.sync(
                [second],
                parse_conversation=parse_conversation,
            )

            first_matches = index.search("unique first")
            second_matches = index.search("unique second")

        self.assertEqual(result.removed, 1)
        self.assertNotIn(first.uuid, first_matches)
        self.assertIn(second.uuid, second_matches)


if __name__ == "__main__":
    unittest.main()
