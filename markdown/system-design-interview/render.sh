#!/usr/bin/env bash
# Render covers and Mermaid diagrams for the System Design Interview series.
#
#   ./render.sh cover 000            assets/000/cover.html  -> cover.png (1500x750)
#   ./render.sh diagrams 000         every assets/000/*.mmd -> matching .png
#   ./render.sh all 000              both
#
# Puppeteer's bundled Chrome will not launch here without --no-sandbox, and it
# fails silently when it cannot, so the flags below are load-bearing.
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${CHROME:-google-chrome}"
PCONF="$(mktemp -d)/pconf.json"
echo '{"args":["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage"]}' > "$PCONF"

cover() {
  local n="$1" dir="assets/$1"
  [[ -f "$dir/cover.html" ]] || { echo "no $dir/cover.html"; exit 1; }
  "$CHROME" --headless --disable-gpu --no-sandbox --disable-dev-shm-usage \
    --hide-scrollbars --window-size=1500,750 \
    --screenshot="$PWD/$dir/cover.png" "file://$PWD/$dir/cover.html" 2>/dev/null
  echo "cover $n -> $dir/cover.png"
}

diagrams() {
  local n="$1" dir="assets/$1" found=0
  for src in "$dir"/*.mmd; do
    [[ -e "$src" ]] || continue
    found=1
    npx -y @mermaid-js/mermaid-cli -i "$src" -o "${src%.mmd}.png" \
      -b white -p "$PCONF" >/dev/null 2>&1
    echo "diagram -> ${src%.mmd}.png"
  done
  [[ $found -eq 1 ]] || echo "no .mmd files in $dir"
}

case "${1:-}" in
  cover)    cover "$2" ;;
  diagrams) diagrams "$2" ;;
  all)      cover "$2"; diagrams "$2" ;;
  *) echo "usage: $0 {cover|diagrams|all} NNN"; exit 1 ;;
esac
