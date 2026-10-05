#!/usr/bin/env bash
# Render covers for the Claude Code series.
#
#   ./render.sh cover 022            assets/022/cover.html -> cover.png (1600x900 @2x)
#   ./render.sh cover 022 023        several at once
#
# The fonts are local files in fonts/ (OFL), so the render never waits on the
# network; --virtual-time-budget still gives @font-face and SVG filters time to
# settle before the screenshot. Headless Chrome needs the sandbox flags below
# and fails silently without them.
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${CHROME:-google-chrome}"

cover() {
  local n="$1" dir="assets/$1"
  [[ -f "$dir/cover.html" ]] || { echo "no $dir/cover.html"; exit 1; }
  "$CHROME" --headless --disable-gpu --no-sandbox --disable-dev-shm-usage \
    --hide-scrollbars --window-size=1600,900 --force-device-scale-factor=2 \
    --virtual-time-budget=3000 \
    --screenshot="$PWD/$dir/cover.png" "file://$PWD/$dir/cover.html" 2>/dev/null
  echo "cover $n -> $dir/cover.png"
}

case "${1:-}" in
  cover) shift; [[ $# -gt 0 ]] || { echo "usage: $0 cover NNN [NNN...]"; exit 1; }
         for n in "$@"; do cover "$n"; done ;;
  *) echo "usage: $0 cover NNN [NNN...]"; exit 1 ;;
esac
