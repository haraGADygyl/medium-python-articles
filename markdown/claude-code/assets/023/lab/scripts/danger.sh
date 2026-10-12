#!/usr/bin/env bash
# Print only the statements in a generated up() that can lose data.
# Usage: scripts/danger.sh out/after.sql
[ -s "$1" ] || { echo "danger.sh: $1 is missing or empty" >&2; exit 2; }
grep -E 'DROP COLUMN|DROP TABLE|ALTER COLUMN .* TYPE|TRUNCATE' "$1" || echo "no destructive statements"
