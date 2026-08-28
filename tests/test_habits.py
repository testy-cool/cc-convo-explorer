import contextlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import agentconvos.scanner as scanner_module
from agentconvos.app import main
from agentconvos.parser import ConversationMeta
from agentconvos.scanner import Project


def _habits_module():
    try:
        from agentconvos import habits
    except ImportError:
        raise AssertionError("agentconvos.habits is not implemented") from None
    return habits


def _synthetic_replies():
    habits = _habits_module()
    replies = []
    for index in range(3):
        delayed = "context " * 61 + "Bottom line: the load-bearing boundary stays."
        replies.append(
            habits.SessionReply(
                session_id=f"fictional-session-{index}",
                project=f"fictional-project-{index}",
                date=f"2026-01-0{index + 1}",
                text=(
                    "First, inspect the fictional input. Then, report the fictional result. "
                    "The honest answer is that the load-bearing boundary needs evidence. "
                    "Two problems remain, and both are yours to decide. "
                    "One is solved. The other is yours to decide. "
                    + delayed
                ),
            )
        )
    return replies


def _meta(path: Path, index: int) -> ConversationMeta:
    return ConversationMeta(
        path=path,
        uuid=f"fictional-session-{index}",
        slug="",
        timestamp=f"2026-01-0{index + 1}T12:00:00Z",
        cwd=f"/fictional/project-{index}",
        preview="fictional prompt",
        source="claude",
    )


def _write_transcript(path: Path, text: str) -> None:
    records = [
        {"type": "user", "message": {"content": "fictional user prompt"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
    ]
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def test_requested_rhetorical_patterns_match_synthetic_examples():
    habits = _habits_module()
    patterns = {pattern.key: pattern for pattern in habits.STRUCTURAL_PATTERNS}
    examples = {
        "honesty_frame": "The honest answer is that the proof is missing.",
        "decision_ownership": "Two problems remain, and both are yours to decide.",
        "remaining_side_handoff": "One is solved. The other is yours to decide.",
        "staged_disclosure": "First, inspect the input. Then, state the result.",
    }

    for key, text in examples.items():
        assert key in patterns
        assert any(habits.variant_matches(variant, text) for variant in patterns[key].variants)


def test_delayed_verdict_only_counts_the_first_marker_after_sixty_words():
    habits = _habits_module()
    pattern = next(item for item in habits.STRUCTURAL_PATTERNS if item.key == "delayed_verdict")
    variant = pattern.variants[0]
    late = "context " * 61 + "Bottom line: ship it."
    early = "Bottom line: wait. " + "context " * 61 + "Bottom line: ship it."

    assert len(habits.variant_matches(variant, late)) == 1
    assert habits.variant_matches(variant, early) == []


def test_analysis_keeps_three_examples_from_three_fictional_sessions():
    habits = _habits_module()
    report = habits.analyze_habits(
        _synthetic_replies(),
        source="claude",
        minimum_sessions=2,
        discovered_limit=5,
    )
    by_key = {pattern.key: pattern for pattern in report.patterns}

    for key in (
        "honesty_frame",
        "decision_ownership",
        "remaining_side_handoff",
        "staged_disclosure",
        "delayed_verdict",
    ):
        assert key in by_key
        assert len(by_key[key].examples) == 3
        assert len({example.session_id for example in by_key[key].examples}) == 3

    discovered = [pattern for pattern in report.patterns if pattern.kind == "Discovered phrase"]
    assert discovered
    assert any("load-bearing boundary" in " ".join(pattern.phrases) for pattern in discovered)
    assert all(len(set(pattern.phrases[0].split())) > 1 for pattern in discovered)


def test_html_has_three_plain_overview_examples_and_no_user_payload():
    habits = _habits_module()
    report = habits.analyze_habits(
        _synthetic_replies(),
        source="claude",
        minimum_sessions=2,
        discovered_limit=3,
    )

    rendered = habits.render_html(report)

    assert "Pattern" in rendered
    assert "Phrases" in rendered
    assert "Examples" in rendered
    assert "Matches" in rendered
    assert rendered.count('data-overview-example="true"') == 3 * len(report.patterns)
    assert "fictional-project" in rendered
    assert "user_message" not in rendered
    assert "preceding user" not in rendered


def test_json_contains_only_the_supplied_fictional_examples():
    habits = _habits_module()
    report = habits.analyze_habits(
        _synthetic_replies(),
        source="claude",
        minimum_sessions=2,
        discovered_limit=2,
    )

    payload = json.dumps(report.public_dict())

    assert "fictional-session" in payload
    assert "/home/" not in payload
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}", payload, re.I)


def test_write_report_creates_only_the_requested_public_safe_artifacts():
    habits = _habits_module()
    report = habits.analyze_habits(
        _synthetic_replies(),
        source="claude",
        minimum_sessions=2,
        discovered_limit=2,
    )
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "fictional-habits.html"

        written = habits.write_report(report, output)

        assert written == output
        assert output.exists()
        assert output.with_suffix(".json").exists()
        assert sorted(path.name for path in Path(tmp).iterdir()) == [
            "fictional-habits.html",
            "fictional-habits.json",
        ]


def test_help_advertises_local_habit_reports():
    stream = io.StringIO()
    old_argv = sys.argv
    sys.argv = ["agentconvos", "--help"]
    try:
        with contextlib.redirect_stdout(stream), pytest.raises(SystemExit) as raised:
            main()
    finally:
        sys.argv = old_argv

    assert raised.value.code == 0
    assert "--habits" in stream.getvalue()
    assert "--output" in stream.getvalue()


def test_habits_requires_exactly_one_source():
    stream = io.StringIO()
    old_argv = sys.argv
    sys.argv = ["agentconvos", "--habits"]
    try:
        with (
            patch("agentconvos.app.ConvoExplorer.run", return_value=None),
            contextlib.redirect_stderr(stream),
            pytest.raises(SystemExit) as raised,
        ):
            main()
    finally:
        sys.argv = old_argv

    assert raised.value.code == 2
    assert "--habits requires exactly one --source" in stream.getvalue()


def test_cli_writes_a_report_from_fictional_assistant_replies_only():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        conversations = []
        for index, reply in enumerate(_synthetic_replies()):
            path = root / f"fictional-{index}.jsonl"
            _write_transcript(path, reply.text)
            conversations.append(_meta(path, index))
        projects = [Project("claude", "/fictional", conversations)]
        output = root / "fictional-report.html"
        stream = io.StringIO()
        old_argv = sys.argv
        sys.argv = [
            "agentconvos",
            "--habits",
            "--source",
            "claude",
            "--output",
            str(output),
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

        rendered = output.read_text(encoding="utf-8")
        payload = output.with_suffix(".json").read_text(encoding="utf-8")

    assert str(output) in stream.getvalue()
    assert "load-bearing boundary" in rendered
    assert "fictional user prompt" not in rendered
    assert "fictional user prompt" not in payload


def test_readme_documents_habits_as_local_candidate_evidence():
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")

    assert "agentconvos --habits --source claude" in readme
    assert "three examples" in readme
    assert "candidate writing patterns" in readme
    assert "does not prove" in readme
