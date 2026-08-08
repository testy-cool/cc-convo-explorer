import inspect
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentconvos import recall


def _event(event_type: str, item: dict | None = None, **extra: object) -> str:
    payload: dict[str, object] = {"type": event_type, **extra}
    if item is not None:
        payload["item"] = item
    return json.dumps(payload) + "\n"


class _FakeStdin(io.StringIO):
    def close(self) -> None:
        self.captured = self.getvalue()
        super().close()


class _FakeProcess:
    def __init__(self, events: list[str], returncode: int = 0):
        self.stdin = _FakeStdin()
        self.stdout = io.StringIO("".join(events))
        self.returncode = returncode
        self.terminated = False

    def wait(self) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


class RecallCommandTests(unittest.TestCase):
    def test_codex_command_requests_json_events_and_a_separate_final_answer(self):
        parameters = inspect.signature(recall._recall_command).parameters
        self.assertIn("answer_path", parameters)
        if "answer_path" not in parameters:
            return
        command = recall._recall_command(
            Path("/tmp/workspace"),
            Path("/tmp/state"),
            Path("/tmp/answer.md"),
        )

        self.assertIn("--json", command)
        self.assertEqual(
            command[command.index("--output-last-message") + 1],
            "/tmp/answer.md",
        )
        self.assertEqual(command[-1], "-")

    def test_agy_command_uses_the_bridge_default_model_and_explicit_workspace(self):
        command = recall._recall_command(
            Path("/tmp/workspace"),
            Path("/tmp/state"),
            Path("/tmp/answer.md"),
            backend="agy",
            prompt="Question from the archive",
        )

        self.assertEqual(
            command[:5],
            [
                "/home/testycool/Work/try-rs/agy-bridge/agy-bridge",
                "run",
                "--workspace",
                "/tmp/workspace",
                "--json",
            ],
        )
        self.assertEqual(command[-1], "Question from the archive")
        self.assertNotIn("--model", command)
        self.assertNotIn("--effort", command)


class RecallProgressTests(unittest.TestCase):
    def test_worker_commentary_does_not_pretend_synthesis_has_started(self):
        progress = recall._RecallProgress("Where was it decided?")

        progress.consume({"type": "thread.started", "thread_id": "thread-1"})
        progress.consume(
            {
                "type": "item.completed",
                "item": {
                    "id": "message-1",
                    "type": "agent_message",
                    "text": "I’ll search alternate wording first.",
                },
            }
        )

        self.assertEqual(progress.stage, 0)
        self.assertIn("planning", progress.latest.casefold())

        progress.consume(
            {
                "type": "item.completed",
                "item": {
                    "id": "message-2",
                    "type": "agent_message",
                    "text": (
                        "Found session 019e3993-458e-76b2-a543-e706db786ae7.\n\n"
                        "Sources: Codex, turn 150"
                    ),
                },
            }
        )
        self.assertEqual(progress.stage, 3)

    def test_progress_tracks_real_searches_candidates_inspection_and_final_match(self):
        progress_type = getattr(recall, "_RecallProgress", None)
        self.assertIsNotNone(progress_type)
        if progress_type is None:
            return
        now = [100.0]
        progress = progress_type(
            "Where was the MCP picker built?",
            clock=lambda: now[0],
        )
        progress.consume(
            {
                "type": "item.started",
                "item": {
                    "id": "search-1",
                    "type": "command_execution",
                    "command": 'agentconvos --search "mcp picker" --json',
                },
            }
        )
        progress.consume(
            {
                "type": "item.completed",
                "item": {
                    "id": "search-1",
                    "type": "command_execution",
                    "command": 'agentconvos --search "mcp picker" --json',
                    "aggregated_output": json.dumps(
                        {
                            "total_searched": 685,
                            "hits": [
                                {"uuid": "session-a"},
                                {"uuid": "session-b"},
                                {"uuid": "session-a"},
                            ],
                        }
                    ),
                },
            }
        )
        progress.consume(
            {
                "type": "item.started",
                "item": {
                    "id": "turns-1",
                    "type": "command_execution",
                    "command": "agentconvos --turns session-a --json",
                },
            }
        )
        now[0] = 112.0
        progress.finish(
            "Found session 019e3993-458e-76b2-a543-e706db786ae7 in "
            "/home/testycool/Work/context-backup/claude-memory-doctor",
            succeeded=True,
        )

        rendered = progress.render_text()
        self.assertIn("CONVERSATION RECALL", rendered)
        self.assertIn("SEARCHES  1", rendered)
        self.assertIn("CANDIDATES  3", rendered)
        self.assertIn("SESSIONS  2", rendered)
        self.assertIn("INSPECTED  1", rendered)
        self.assertIn("00:12", rendered)
        self.assertIn("019e3993-458e-76b2-a543-e706db786ae7", rendered)
        self.assertIn("claude-memory-doctor", rendered)
        self.assertNotIn("gpt-5.6", rendered.casefold())
        self.assertNotIn("luna", rendered.casefold())


class RecallStreamingTests(unittest.TestCase):
    def test_clihow_stream_flag_forces_tty_only_while_enabled(self):
        stream = io.StringIO()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLIHOW_STREAM_TTY", None)
            self.assertFalse(recall._is_tty(stream))

            os.environ["CLIHOW_STREAM_TTY"] = "1"
            self.assertTrue(recall._is_tty(stream))

            os.environ["CLIHOW_STREAM_TTY"] = "0"
            self.assertFalse(recall._is_tty(stream))

    def test_recall_prompt_labels_clihow_answers_as_navigation_context(self):
        prompt = recall._recall_prompt("What changed?", Path("/work/demo"))
        self.assertIn("Clihow threads are prior retrieval transcripts", prompt)
        self.assertIn("navigation", prompt.casefold())
        self.assertIn("verify every material claim", prompt)

    def test_non_tty_stream_is_plain_and_stdout_contains_only_the_final_answer(self):
        signature = inspect.signature(recall.run_recall)
        self.assertIn("process_factory", signature.parameters)
        self.assertIn("state_dir", signature.parameters)
        self.assertIn("stdout", signature.parameters)
        self.assertIn("stderr", signature.parameters)
        if "process_factory" not in signature.parameters:
            return

        events = [
            _event("thread.started", thread_id="thread-1"),
            _event(
                "item.started",
                {
                    "id": "item-1",
                    "type": "command_execution",
                    "command": 'agentconvos --search "mcp picker" --json',
                },
            ),
            _event(
                "item.completed",
                {
                    "id": "item-1",
                    "type": "command_execution",
                    "command": 'agentconvos --search "mcp picker" --json',
                    "aggregated_output": json.dumps(
                        {"total_searched": 685, "hits": [{"uuid": "session-a"}]}
                    ),
                    "exit_code": 0,
                    "status": "completed",
                },
            ),
            _event(
                "item.completed",
                {"id": "item-2", "type": "agent_message", "text": "fallback"},
            ),
            _event("turn.completed", usage={"output_tokens": 10}),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        created: list[_FakeProcess] = []

        def process_factory(command: list[str], **kwargs: object) -> _FakeProcess:
            answer_path = Path(command[command.index("--output-last-message") + 1])
            answer_path.write_text("The matched conversation.\n\nSources: session-a\n")
            process = _FakeProcess(events)
            created.append(process)
            self.assertEqual(kwargs["stderr"], -2)
            return process

        with tempfile.TemporaryDirectory(prefix="agentconvos-recall-test-") as temporary:
            exit_code = recall.run_recall(
                "Where was the MCP picker built?",
                origin=Path(temporary),
                process_factory=process_factory,
                state_dir=Path(temporary) / "state",
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            stdout.getvalue(),
            "The matched conversation.\n\nSources: session-a\n",
        )
        self.assertIn("Searching archive", stderr.getvalue())
        self.assertNotIn("thread.started", stderr.getvalue())
        self.assertNotIn("\x1b[", stderr.getvalue())
        self.assertEqual(len(created), 1)
        self.assertIn("untrusted data", created[0].stdin.captured)

    def test_agy_backend_returns_the_bridge_answer(self):
        bridge_result = {
            "answer": "The matched conversation.\n\nSources: session-a\n",
            "conversation_id": "bridge-session",
            "effort": "high",
            "exit_code": 0,
            "model": "gemini-3.6-flash",
            "ok": True,
            "stderr": "",
            "timed_out": False,
        }
        stdout = io.StringIO()
        stderr = io.StringIO()
        created: list[_FakeProcess] = []

        def process_factory(command: list[str], **kwargs: object) -> _FakeProcess:
            self.assertEqual(command[0], recall._AGY_BRIDGE)
            self.assertEqual(command[1:5], ["run", "--workspace", command[3], "--json"])
            self.assertEqual(command[-1], recall._recall_prompt("Where was it?", Path.cwd()))
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            process = _FakeProcess([json.dumps(bridge_result) + "\n"])
            created.append(process)
            return process

        with tempfile.TemporaryDirectory(prefix="agentconvos-recall-test-") as temporary:
            exit_code = recall.run_recall(
                "Where was it?",
                backend="agy",
                origin=Path.cwd(),
                process_factory=process_factory,
                state_dir=Path(temporary) / "state",
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), bridge_result["answer"])
        self.assertIn("querying AGY", stderr.getvalue())
        self.assertEqual(len(created), 1)

    def test_agy_backend_surfaces_bridge_provider_errors(self):
        bridge_result = {
            "answer": "",
            "exit_code": 7,
            "ok": False,
            "stderr": "provider quota exhausted",
            "timed_out": False,
        }
        stdout = io.StringIO()
        stderr = io.StringIO()

        def process_factory(command: list[str], **kwargs: object) -> _FakeProcess:
            return _FakeProcess([json.dumps(bridge_result) + "\n"], returncode=7)

        with tempfile.TemporaryDirectory(prefix="agentconvos-recall-test-") as temporary:
            exit_code = recall.run_recall(
                "Where was it?",
                backend="agy",
                origin=Path(temporary),
                process_factory=process_factory,
                state_dir=Path(temporary) / "state",
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 7)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("AGY bridge/provider failed", stderr.getvalue())
        self.assertIn("provider quota exhausted", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
