#!/usr/bin/env bash
# Dry-run migration:generate against the migrated database and keep only the
# SQL in up(). Usage: scripts/generate.sh before|after [output-name]
set -euo pipefail
cd "$(dirname "$0")/.."
stage="$1"; name="${2:-$1}"
LAB_ENTITIES="$stage" FORCE_COLOR=0 npx typeorm-ts-node-commonjs \
  migration:generate -d src/data-source.ts --dr src/migrations/Probe \
  | sed -n '/public async up/,/^    }/p' \
  | grep -o 'query(`.*`)' | sed 's/^query(`//; s/`)$//' \
  > "out/$name.sql"
echo "$name: $(wc -l < "out/$name.sql") statements in up()"
