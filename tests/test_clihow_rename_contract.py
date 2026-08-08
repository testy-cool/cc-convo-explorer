import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentconvos import scanner
from agentconvos.app import _resume_cmd
from agentconvos.parser import _detect_format, get_meta

THREAD_ID = "019f0000-0000-7000-8000-000000000001"


class ClihowRenameContractTests(unittest.TestCase):
    def test_discovers_and_resumes_clihow_threads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            threads = root / "threads"
            threads.mkdir()
            path = threads / f"{THREAD_ID}.jsonl"
            path.write_text(
                json.dumps(
                    {
                        "type": "clihow_thread",
                        "schemaVersion": 1,
                        "id": THREAD_ID,
                        "title": "Find the conversation",
                        "scope": "agentconvos",
                        "cwd": "/work/demo",
                        "createdAt": "2026-08-02T00:00:00.000Z",
                        "updatedAt": "2026-08-02T00:00:01.000Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertEqual(_detect_format(path), "clihow")
            meta = get_meta(path)
            self.assertIsNotNone(meta)
            assert meta is not None
            self.assertEqual(meta.source, "clihow")
            self.assertEqual(_resume_cmd("clihow", THREAD_ID), ["clihow", "ask", "--thread", THREAD_ID])

            with patch.dict(os.environ, {"CLIHOW_HOME": str(root)}, clear=False), patch.object(
                scanner, "_CACHE_PATH", root / "cache.json"
            ):
                projects = scanner.scan_projects(source="clihow")
            self.assertEqual([c.uuid for p in projects for c in p.conversations], [THREAD_ID])


if __name__ == "__main__":
    unittest.main()
