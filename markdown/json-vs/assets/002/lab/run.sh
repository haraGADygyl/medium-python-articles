#!/usr/bin/env bash
# Start a throwaway PostgreSQL 18, run every experiment, remove it.
set -euo pipefail
cd "$(dirname "$0")"
NAME=json-vs-lab-002
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=lab \
  -p 127.0.0.1:55002:5432 postgres:18.0 >/dev/null
trap 'docker rm -f "$NAME" >/dev/null' EXIT
until docker exec "$NAME" pg_isready -U postgres -q; do sleep 1; done
sleep 2   # the entrypoint restarts the server once after initdb

python3 matrix.py | tee output-matrix.txt
python3 pipeline.py | tee output-pipeline.txt
python3 snippets.py | tee output-snippets.txt
