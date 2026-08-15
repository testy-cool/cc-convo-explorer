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
  echo "wrote assets/$name.png"
}

shoot demo        "$DEMO/work/checkout-service" 'agentconvos --context'
shoot demo-search "$DEMO/work/checkout-service" 'agentconvos --search rate'
shoot demo-help   "$DEMO"                       'agentconvos --help'

# The browser redraws over itself, so termshot cannot capture it. Textual
# exports its own screenshot instead.
$PY "$REPO/scripts/capture_tui.py" "$DEMO" "$REPO/assets/demo-tui.svg" "rate limit"
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
