#!/usr/bin/env bash
# Recreate the database as production has it: both hand-written migrations
# applied, a few rows seeded, no fix yet.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --wait >/dev/null
docker exec doc-drift-lab-db dropdb -U lab --if-exists trial
docker exec doc-drift-lab-db dropdb -U lab --if-exists cashouts
docker exec doc-drift-lab-db createdb -U lab cashouts
FORCE_COLOR=0 npx typeorm-ts-node-commonjs migration:run -d src/data-source.ts >/dev/null
docker exec -i doc-drift-lab-db psql -U lab -d cashouts -q < scripts/seed.sql
