#!/usr/bin/env bash
# Apply a generated up() to a throwaway copy of the database and print what is
# left. Usage: scripts/apply-generated.sh out/after.sql all|none
set -uo pipefail
sql="$1"; mode="$2"
db() { docker exec -i doc-drift-lab-db "$@"; }
db dropdb -U lab --if-exists trial 2>/dev/null
db createdb -U lab -T cashouts trial
if [ "$mode" = all ]; then
  { echo "BEGIN;"; sed 's/$/;/' "$sql"; echo "COMMIT;"; } \
    | db psql -U lab -d trial -q -v ON_ERROR_STOP=1 2>&1 | grep ERROR
else
  sed 's/$/;/' "$sql" | db psql -U lab -d trial -q 2>&1 | grep -c ERROR | sed 's/$/ statements failed/'
fi
db psql -U lab -d trial -c "TABLE cashouts" -c "TABLE cashout_accounts"
