"""Keep the test suite away from the archive of whoever is running it.

Several tests build a ConvoExplorer with a handful of fixture conversations
and no explicit index. Without this, that index defaults to the real one under
$HOME, and syncing a fixture list against it deletes every conversation the
fixtures do not mention: running the tests wipes the developer's search index
and costs them a full reindex of their archive.
"""

import tempfile
from pathlib import Path

import pytest

import agentconvos.scanner as scanner_module
import agentconvos.search_index as search_index_module


@pytest.fixture(autouse=True)
def isolate_local_state(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="agentconvos-tests-") as tmp:
        root = Path(tmp)
        monkeypatch.setattr(
            search_index_module,
            "DEFAULT_INDEX_PATH",
            root / "search-index.sqlite3",
        )
        monkeypatch.setattr(
            scanner_module,
            "_CACHE_PATH",
            root / "meta-cache.json",
        )
        yield root
