"""Persistent incremental full-text index for conversation search."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable

from .parser import (
    ConversationMeta,
    Turn,
    conversation_signature,
    parse_jsonl,
    parse_search_terms,
)


DEFAULT_INDEX_PATH = Path.home() / ".claude" / "convo-explorer" / "search-index.sqlite3"


@dataclass(frozen=True)
class IndexSyncStats:
    total: int
    checked: int = 0
    indexed: int = 0
    unchanged: int = 0
    removed: int = 0
    failed: int = 0


class ConversationSearchIndex:
    """SQLite FTS5 index keyed by transcript path, size, and mtime."""

    def __init__(self, path: Path = DEFAULT_INDEX_PATH) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS search_documents (
                path TEXT PRIMARY KEY,
                uuid TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                metadata_key TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS search_documents_fts USING fts5(
                uuid UNINDEXED,
                path UNINDEXED,
                metadata,
                content,
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )
        return connection

    @staticmethod
    def _metadata(meta: ConversationMeta) -> str:
        return "\n".join(
            value
            for value in (
                meta.uuid,
                meta.slug,
                meta.source,
                meta.cwd,
                meta.git_branch,
                meta.preview,
            )
            if value
        )

    def sync(
        self,
        conversations: Iterable[ConversationMeta],
        *,
        parse_conversation: Callable[[Path], list[Turn]] = parse_jsonl,
        on_progress: Callable[[IndexSyncStats], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> IndexSyncStats:
        metas = list(conversations)
        stats = IndexSyncStats(total=len(metas))
        connection = self._connect()
        try:
            existing = {
                row[0]: row[1:]
                for row in connection.execute(
                    "SELECT path, uuid, size, mtime_ns, metadata_key FROM search_documents"
                )
            }
            current_paths = {str(meta.path) for meta in metas}
            stale_paths = set(existing) - current_paths
            if stale_paths:
                with connection:
                    for stale_path in stale_paths:
                        connection.execute(
                            "DELETE FROM search_documents_fts WHERE path = ?",
                            (stale_path,),
                        )
                        connection.execute(
                            "DELETE FROM search_documents WHERE path = ?",
                            (stale_path,),
                        )
                stats = replace(stats, removed=len(stale_paths))

            for meta in metas:
                if should_cancel and should_cancel():
                    break

                path_key = str(meta.path)
                metadata = self._metadata(meta)
                try:
                    size_bytes, mtime_ns = conversation_signature(meta.path)
                    signature = (
                        meta.uuid,
                        size_bytes,
                        mtime_ns,
                        metadata,
                    )
                    if existing.get(path_key) == signature:
                        stats = replace(
                            stats,
                            checked=stats.checked + 1,
                            unchanged=stats.unchanged + 1,
                        )
                    else:
                        turns = parse_conversation(meta.path)
                        content = "\n".join(turn.text for turn in turns if turn.text)
                        with connection:
                            connection.execute(
                                "DELETE FROM search_documents_fts WHERE path = ?",
                                (path_key,),
                            )
                            connection.execute(
                                "INSERT INTO search_documents_fts "
                                "(uuid, path, metadata, content) VALUES (?, ?, ?, ?)",
                                (meta.uuid, path_key, metadata, content),
                            )
                            connection.execute(
                                """
                                INSERT INTO search_documents
                                    (path, uuid, size, mtime_ns, metadata_key)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(path) DO UPDATE SET
                                    uuid = excluded.uuid,
                                    size = excluded.size,
                                    mtime_ns = excluded.mtime_ns,
                                    metadata_key = excluded.metadata_key
                                """,
                                (
                                    path_key,
                                    meta.uuid,
                                    size_bytes,
                                    mtime_ns,
                                    metadata,
                                ),
                            )
                        stats = replace(
                            stats,
                            checked=stats.checked + 1,
                            indexed=stats.indexed + 1,
                        )
                except (OSError, sqlite3.Error, ValueError):
                    stats = replace(
                        stats,
                        checked=stats.checked + 1,
                        failed=stats.failed + 1,
                    )

                if on_progress:
                    on_progress(stats)
            return stats
        finally:
            connection.close()

    @staticmethod
    def _match_expression(query: str) -> str:
        expressions: list[str] = []
        for term in parse_search_terms(query):
            tokens = re.findall(r"\w+", term, flags=re.UNICODE)
            if not tokens:
                continue
            escaped = [token.replace('"', '""') for token in tokens]
            if len(escaped) == 1:
                expressions.append(f'"{escaped[0]}"*')
            else:
                expressions.append(f'"{" ".join(escaped)}"')
        return " AND ".join(expressions)

    def search(
        self,
        query: str,
        limit: int = 5000,
        snippet_limit: int = 20,
    ) -> dict[str, str]:
        expression = self._match_expression(query)
        if not expression or not self.path.exists():
            return {}

        connection = sqlite3.connect(
            f"file:{self.path}?mode=ro",
            uri=True,
            timeout=0.1,
        )
        try:
            matches = {
                uuid: ""
                for (uuid,) in connection.execute(
                    """
                    SELECT uuid
                    FROM search_documents_fts
                    WHERE search_documents_fts MATCH ?
                    LIMIT ?
                    """,
                    (expression, limit),
                )
            }
            if not matches or snippet_limit <= 0:
                return matches

            snippet_rows = connection.execute(
                """
                SELECT uuid,
                       snippet(search_documents_fts, 3, '', '', ' … ', 18)
                FROM search_documents_fts
                WHERE content MATCH ?
                LIMIT ?
                """,
                (expression, min(limit, snippet_limit)),
            )
            for uuid, snippet in snippet_rows:
                matches[uuid] = snippet or ""
            return matches
        except sqlite3.Error:
            return {}
        finally:
            connection.close()
