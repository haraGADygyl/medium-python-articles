#!/usr/bin/env bash
# Render covers for the Claude Code series.
#
#   ./render.sh cover 022            assets/022/cover.html -> cover.jpg (1500x750)
#   ./render.sh cover 022 023        several at once
#
# 1500x750 at 1x as a high-quality JPEG (~300 KB), chosen by the author over
# 1600x900 and 2x renders (up to 4.3 MB as PNG) as looking fine for a cover. The paper grain is per-pixel noise, which is why PNG is the wrong format.
# Fonts are local files in fonts/ (OFL); --virtual-time-budget lets @font-face and
# the SVG filters settle. Headless Chrome needs the sandbox flags below and fails
# silently without them. Needs ffmpeg for the PNG -> JPEG step.
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${CHROME:-google-chrome}"

cover() {
  local n="$1" dir="assets/$1" tmp
  [[ -f "$dir/cover.html" ]] || { echo "no $dir/cover.html"; exit 1; }
  tmp="$(mktemp --suffix=.png)"
  "$CHROME" --headless --disable-gpu --no-sandbox --disable-dev-shm-usage \
    --hide-scrollbars --window-size=1500,750 --force-device-scale-factor=1 \
    --virtual-time-budget=3000 \
    --screenshot="$tmp" "file://$PWD/$dir/cover.html" 2>/dev/null
  ffmpeg -loglevel error -y -i "$tmp" -q:v 2 "$dir/cover.jpg"
  rm -f "$tmp"
  echo "cover $n -> $dir/cover.jpg ($(du -h "$dir/cover.jpg" | cut -f1))"
}

case "${1:-}" in
  cover) shift; [[ $# -gt 0 ]] || { echo "usage: $0 cover NNN [NNN...]"; exit 1; }
         for n in "$@"; do cover "$n"; done ;;
  *) echo "usage: $0 cover NNN [NNN...]"; exit 1 ;;
esac
