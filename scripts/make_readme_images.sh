#!/usr/bin/env bash
# Rebuild every README image from a synthetic archive.
#
# Needs termshot (https://github.com/homeport/termshot) and tmux on PATH.
# termshot reads the terminal size, so it is run inside tmux where it has a
# real terminal to ask.
#
#   ./scripts/make_readme_images.sh

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO="${DEMO_HOME:-/tmp/agentconvos-demo}"
COLS=124
PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || PY=python

for tool in termshot tmux; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "error: $tool is not on PATH" >&2
    echo "  termshot: go install github.com/homeport/termshot/cmd/termshot@latest" >&2
    exit 1
  }
done

# Each capture runs behind tmux, so a failure there is invisible to this
# script. Refuse to claim success for an image that was never written.
assert_written() {
  local file="$1"
  [ -s "$file" ] || { echo "error: $file was not written" >&2; exit 1; }
}

$PY "$REPO/scripts/make_demo_archive.py" "$DEMO"

# A short name on PATH so the captured command reads "agentconvos", not the
# full path to the virtual environment.
mkdir -p "$DEMO/bin"
ln -sf "$REPO/.venv/bin/agentconvos" "$DEMO/bin/agentconvos"

shoot() {
  # $3 is a command line, already quoted the way a user would type it.
  local name="$1" workdir="$2" cmd="$3"
  rm -f "$REPO/assets/$name.png"
  tmux kill-session -t acshot 2>/dev/null || true
  tmux new-session -d -s acshot -x 160 -y 70 -c "$workdir" \
    "HOME=$DEMO PATH=$DEMO/bin:\$PATH termshot --show-cmd --columns $COLS \
       --filename $REPO/assets/$name.png -- $cmd ; echo SHOT_DONE; sleep 60"
  timeout 90 bash -c \
    'until tmux capture-pane -t acshot -p 2>/dev/null | grep -q SHOT_DONE; do sleep 0.4; done'
  tmux kill-session -t acshot 2>/dev/null || true
  assert_written "$REPO/assets/$name.png"
  echo "wrote assets/$name.png"
}

# recall paints a progress display that redraws in place. Running it straight
# through termshot stacks every redraw into one enormous image, so its final
# screen is taken from tmux and rendered from that instead.
shoot_frame() {
  # $4, when given, must appear in the captured frame. A run that failed still
  # paints a screen, and an image of a stack trace is worse than no image.
  local name="$1" workdir="$2" cmd="$3" expect="${4:-}"
  local raw="$DEMO/.frame.txt"
  rm -f "$REPO/assets/$name.png"
  tmux kill-session -t acshot 2>/dev/null || true
  # The pane has to be exactly as wide as the render, or tmux wraps the text
  # once and termshot wraps the wrapped text again.
  tmux new-session -d -s acshot -x $COLS -y 90 -c "$workdir" \
    "printf '\033[32m→\033[0m %s\n' '$cmd'; HOME=$DEMO PATH=$DEMO/bin:\$PATH $cmd; \
     echo SHOT_DONE; sleep 300"
  timeout 600 bash -c \
    'until tmux capture-pane -t acshot -p 2>/dev/null | grep -q SHOT_DONE; do sleep 1; done'
  tmux capture-pane -e -p -t acshot | sed '/SHOT_DONE/,$d' > "$raw"
  tmux kill-session -t acshot 2>/dev/null || true
  if [ -n "$expect" ] && ! grep -q "$expect" "$raw"; then
    echo "error: $name run did not produce '$expect'; see $raw" >&2
    exit 1
  fi
  termshot --raw-read "$raw" --columns $COLS --filename "$REPO/assets/$name.png"
  assert_written "$REPO/assets/$name.png"
  echo "wrote assets/$name.png"
}

shoot demo        "$DEMO/work/checkout-service" 'agentconvos --context'
shoot demo-search "$DEMO/work/checkout-service" 'agentconvos --search rate'
shoot demo-help   "$DEMO"                       'agentconvos --help'

# recall spends a real model call, so it is only captured when the AGY bridge
# is present. The bridge is used rather than the default Codex backend because
# it authenticates locally: Codex looks for credentials under HOME, which here
# is the throwaway demo archive. Headless runs cannot prompt for tool
# permission either, so the demo home gets a settings file that grants it.
AGY=/home/testycool/Work/try-rs/agy-bridge/agy-bridge
if [ -x "$AGY" ] && [ "${SKIP_RECALL:-}" != "1" ]; then
  mkdir -p "$DEMO/.gemini/antigravity-cli"
  cat > "$DEMO/.gemini/antigravity-cli/settings.json" <<JSON
{
  "toolPermission": "always-proceed",
  "trustedWorkspaces": ["$DEMO", "/tmp"]
}
JSON
  shoot_frame demo-recall "$DEMO/work/checkout-service" \
    'agentconvos recall --backend agy "Where did we decide to use soft deletes, and why?"' \
    "Sources"
else
  echo "skipping assets/demo-recall.png (no AGY bridge, or SKIP_RECALL=1)"
fi

# The browser redraws over itself, so termshot cannot capture it. Textual
# exports its own screenshot instead.
$PY "$REPO/scripts/capture_tui.py" "$DEMO" "$REPO/assets/demo-tui.svg" "rate limit"
assert_written "$REPO/assets/demo-tui.svg"
echo "wrote assets/demo-tui.svg"

# A terminal capture uses a handful of colours, so a palette cuts the file size
# by more than half with nothing visible lost.
if command -v uv >/dev/null 2>&1; then
  (cd "$REPO" && uv run --quiet --with pillow python - <<'PY'
from pathlib import Path

from PIL import Image

for path in sorted(Path("assets").glob("*.png")):
    before = path.stat().st_size
    image = Image.open(path).convert("RGB")
    image.quantize(colors=128, method=Image.MEDIANCUT).save(path, optimize=True)
    print(f"  {path.name}: {before // 1024}k -> {path.stat().st_size // 1024}k")
PY
  )
fi
