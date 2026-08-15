"""Export an SVG screenshot of the browser for the README.

Textual renders the screenshot itself, so the image is the real app rather
than a drawing. termshot cannot do this one, because a full screen app
redraws over itself and only the final frame is wanted.

Usage:
    python scripts/capture_tui.py /tmp/demohome assets/tui.svg "rate limit"
"""

import asyncio
import os
import sys
from pathlib import Path

HOME = sys.argv[1]
OUT = Path(sys.argv[2])
QUERY = sys.argv[3] if len(sys.argv) > 3 else ""

# The app reads the archive under HOME, so point it at the demo archive
# before importing anything that resolves those paths.
os.environ["HOME"] = HOME

from textual.widgets import Input, Tree  # noqa: E402

from agentconvos.app import ConvoExplorer  # noqa: E402


async def main():
    app = ConvoExplorer()
    async with app.run_test(size=(124, 44)) as pilot:
        tree = app.query_one("#nav-tree", Tree)

        # Wait for the scan to put conversations in the tree.
        for _ in range(200):
            await pilot.pause(0.05)
            if tree.root.children:
                break

        if QUERY:
            app.query_one("#filter-input", Input).value = QUERY
            for _ in range(60):
                await pilot.pause(0.05)

            # Enter opens the highlighted result and moves focus to the tree,
            # which is also what makes the footer show the conversation keys
            # instead of only the two that work while typing.
            await pilot.press("enter")
            for _ in range(60):
                await pilot.pause(0.05)

        OUT.write_text(app.export_screenshot(title="agentconvos"), encoding="utf-8")
        print(f"wrote {OUT}")


asyncio.run(main())
