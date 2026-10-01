#!/usr/bin/env bash
# Render covers for the Python series.
#
#   ./render.sh cover 137            assets/137/cover.html -> cover.png (1500x750)
#   ./render.sh cover 120 121 122    several at once, for backfilling older articles
#
# Headless Chrome needs the sandbox flags below and fails silently without them.
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${CHROME:-google-chrome}"

cover() {
  local n="$1" dir="assets/$1"
  [[ -f "$dir/cover.html" ]] || { echo "no $dir/cover.html"; exit 1; }
  "$CHROME" --headless --disable-gpu --no-sandbox --disable-dev-shm-usage \
    --hide-scrollbars --window-size=1500,750 \
    --screenshot="$PWD/$dir/cover.png" "file://$PWD/$dir/cover.html" 2>/dev/null
  echo "cover $n -> $dir/cover.png"
}

case "${1:-}" in
  cover) shift; [[ $# -gt 0 ]] || { echo "usage: $0 cover NNN [NNN...]"; exit 1; }
         for n in "$@"; do cover "$n"; done ;;
  *) echo "usage: $0 cover NNN [NNN...]"; exit 1 ;;
esac
