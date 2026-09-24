#!/usr/bin/env bash
# Render covers and Mermaid diagrams for the System Design Interview series.
#
#   ./render.sh cover 000            assets/000/cover.html  -> cover.png (1500x750)
#   ./render.sh diagrams 000         every assets/000/*.mmd -> matching .png
#   ./render.sh all 000              both
#   ./render.sh gif 004 01-loop      assets/004/01-loop.gif, animated
#
# gif: a flowchart animates the edges declared with `e1@{ animate: true }`, and
# reads 01-loop.anim.mmd when it exists so the static PNG keeps solid edges; a
# sequence diagram reveals one message or note at a time and needs no changes.
# Needs `npm install` in tools/ once.
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
    [[ "$src" == *.anim.mmd ]] && continue   # animation-only sources
    found=1
    npx -y @mermaid-js/mermaid-cli -i "$src" -o "${src%.mmd}.png" \
      -b white -p "$PCONF" >/dev/null 2>&1
    echo "diagram -> ${src%.mmd}.png"
  done
  [[ $found -eq 1 ]] || echo "no .mmd files in $dir"
}

gif() {
  local n="$1" name="$2" dir="assets/$1" src
  src="$dir/$name.anim.mmd"
  [[ -f "$src" ]] || src="$dir/$name.mmd"
  [[ -f "$src" ]] || { echo "no $dir/$name.mmd"; exit 1; }
  [[ -d tools/node_modules ]] || (cd tools && npm install --silent)
  node tools/animate.mjs "$src" "$dir/$name.gif"
}

case "${1:-}" in
  cover)    cover "$2" ;;
  diagrams) diagrams "$2" ;;
  all)      cover "$2"; diagrams "$2" ;;
  gif)      gif "$2" "$3" ;;
  *) echo "usage: $0 {cover|diagrams|all} NNN | $0 gif NNN name"; exit 1 ;;
esac
