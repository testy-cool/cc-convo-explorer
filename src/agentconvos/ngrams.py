"""Deterministic lexical comparison of agent reply text."""

from __future__ import annotations

import math
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .parser import DETAIL_TEXT, parse_jsonl
from .scanner import Project

_STOPWORDS = frozenset(
    """
    a about above after again against all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for from
    further had has have having he her here hers herself him himself his how i if in into is it
    its itself just me more most my myself no nor not now of off on once only or other our ours
    ourselves out over own same she should so some such than that the their theirs them themselves
    then there these they this those through to too under until up very was we were what when where
    which while who whom why will with would you your yours yourself yourselves
    i'd i'll i'm i've we'd we'll we're we've they'd they'll they're they've you'd you'll you're you've
    """.split()
)
_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_PATH_OR_IDENTIFIER = re.compile(
    r"(?<!\S)\S*(?:[/\\]|_|[0-9]|\.[a-zA-Z0-9]{1,8}(?:\W|$))\S*"
)
_SEGMENT_BREAK = re.compile(r"[.!?;:\n\r|{}\[\]()<>=]+|\s[-–—]{2,}\s")
_TOKEN = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)


@dataclass(frozen=True)
class PhraseResult:
    phrase: str
    occurrences: int
    sessions: int
    distinctiveness: float
    distinctiveness_label: str
    ranking_score: float

    def public_dict(self) -> dict:
        row = asdict(self)
        row.pop("ranking_score")
        return row


@dataclass(frozen=True)
class NgramAnalysis:
    source: str
    target_sessions: int
    baseline_sessions: int
    phrases: list[PhraseResult]

    def public_dict(self) -> dict:
        return {
            "source": self.source,
            "comparison_baseline": "all other indexed agent sources",
            "target_sessions": self.target_sessions,
            "baseline_sessions": self.baseline_sessions,
            "phrases": [row.public_dict() for row in self.phrases],
        }


def _segments(text: str) -> list[list[str]]:
    text = _FENCED_CODE.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _PATH_OR_IDENTIFIER.sub(" . ", text)
    segments: list[list[str]] = []
    for raw_segment in _SEGMENT_BREAK.split(text):
        tokens = [token.casefold() for token in _TOKEN.findall(raw_segment)]
        tokens = [token for token in tokens if 1 < len(token) <= 40]
        if tokens:
            segments.append(tokens)
    return segments


def phrases(text: str) -> list[str]:
    """Return useful one-to-three-word phrases, preserving internal hyphens."""
    found: list[str] = []
    for tokens in _segments(text):
        for size in (1, 2, 3):
            for start in range(len(tokens) - size + 1):
                words = tokens[start : start + size]
                if words[0] in _STOPWORDS or words[-1] in _STOPWORDS:
                    continue
                found.append(" ".join(words))
    return found


def assistant_reply_text(path: Path) -> str:
    """Return normalized assistant reply text without tools, results, or reasoning."""
    return "\n".join(
        turn.text
        for turn in parse_jsonl(path, detail=DETAIL_TEXT)
        if turn.role == "assistant" and turn.text.strip()
    )


def assistant_replies_from_index(index_path: Path, conversations: list) -> dict[str, str]:
    """Read assistant turns for known conversations from the search index."""
    requested_paths = {str(conversation.path) for conversation in conversations}
    replies: dict[str, list[str]] = {}
    connection = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT path, content FROM search_turns_fts WHERE role = 'assistant'"
        )
        for path, content in rows:
            if path in requested_paths and content:
                replies.setdefault(path, []).append(content)
    finally:
        connection.close()
    return {path: "\n".join(parts) for path, parts in replies.items()}


def rank_phrases(
    target_sessions: list[str],
    baseline_sessions: list[str],
    *,
    limit: int = 50,
) -> list[PhraseResult]:
    """Rank phrases by smoothed session-prevalence ratio and target coverage."""
    target_occurrences: Counter[str] = Counter()
    target_documents: Counter[str] = Counter()
    baseline_documents: Counter[str] = Counter()

    for text in target_sessions:
        session_phrases = phrases(text)
        target_occurrences.update(session_phrases)
        target_documents.update(set(session_phrases))
    for text in baseline_sessions:
        baseline_documents.update(set(phrases(text)))

    target_total = len(target_sessions)
    baseline_total = len(baseline_sessions)
    minimum_sessions = 2 if target_total > 1 else 1
    ranked: list[PhraseResult] = []
    for phrase, session_count in target_documents.items():
        if session_count < minimum_sessions:
            continue
        target_rate = (session_count + 0.5) / (target_total + 1)
        baseline_rate = (baseline_documents[phrase] + 0.5) / (baseline_total + 1)
        ratio = target_rate / baseline_rate
        if ratio <= 1:
            continue
        ranking_score = math.log2(ratio) * math.log2(session_count + 1)
        ranked.append(
            PhraseResult(
                phrase=phrase,
                occurrences=target_occurrences[phrase],
                sessions=session_count,
                distinctiveness=round(ratio, 2),
                distinctiveness_label=f"{ratio:.1f}× more prevalent across sessions",
                ranking_score=ranking_score,
            )
        )

    ranked.sort(
        key=lambda row: (
            -row.ranking_score,
            -row.sessions,
            -row.occurrences,
            row.phrase,
        )
    )
    return ranked[: max(1, limit)]


def analyze_projects(
    projects: list[Project],
    source: str,
    *,
    limit: int = 50,
    indexed_replies: dict[str, str] | None = None,
) -> NgramAnalysis:
    target_sessions: list[str] = []
    baseline_sessions: list[str] = []
    for project in projects:
        for conversation in project.conversations:
            text = (indexed_replies or {}).get(str(conversation.path))
            if text is None:
                text = assistant_reply_text(conversation.path)
            if not text:
                continue
            destination = target_sessions if conversation.source == source else baseline_sessions
            destination.append(text)

    return NgramAnalysis(
        source=source,
        target_sessions=len(target_sessions),
        baseline_sessions=len(baseline_sessions),
        phrases=rank_phrases(target_sessions, baseline_sessions, limit=limit),
    )
