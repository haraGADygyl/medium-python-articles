#!/usr/bin/env bash
# Start a throwaway PostgreSQL 18, run every experiment, remove it.
set -euo pipefail
cd "$(dirname "$0")"
NAME=json-vs-lab-001
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=lab \
  -p 127.0.0.1:55001:5432 postgres:18.0 >/dev/null
trap 'docker rm -f "$NAME" >/dev/null' EXIT
until docker exec "$NAME" pg_isready -U postgres -q; do sleep 1; done
sleep 2   # the entrypoint restarts the server once after initdb

python3 measure.py | tee output-jsonb.txt
docker exec -i "$NAME" psql -U postgres -X < semantics.sql > output-semantics.txt 2>&1
cat output-semantics.txt
