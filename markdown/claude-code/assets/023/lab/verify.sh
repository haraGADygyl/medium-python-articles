#!/usr/bin/env bash
# Rebuild the lab from scratch and check every number the article quotes.
set -euo pipefail
cd "$(dirname "$0")"
export FORCE_COLOR=0
fail() { echo "FAIL: $*"; exit 1; }
drops() { grep -c 'DROP COLUMN' "$1" || true; }

scripts/reset.sh

scripts/generate.sh before
scripts/generate.sh after
scripts/generate.sh no-relation
[ "$(drops out/before.sql)" = 6 ] || fail "before: expected 6 DROP COLUMN"
[ "$(drops out/after.sql)" = 3 ] || fail "after: expected 3 DROP COLUMN"
[ "$(drops out/no-relation.sql)" = 1 ] || fail "no-relation: expected 1 DROP COLUMN"
grep -q 'DROP COLUMN "account_id"' out/after.sql && fail "after: account_id should be clean"
echo "OK  DROP COLUMN: before 6, after 3, no-relation 1"

scripts/apply-generated.sh out/after.sql all > out/apply-after-all.txt
scripts/apply-generated.sh out/after.sql none > out/apply-after-none.txt
scripts/apply-generated.sh out/before.sql none > out/apply-before-none.txt
grep -q 'contains null values' out/apply-after-all.txt || fail "transaction run should fail"
grep -q '9001' out/apply-after-all.txt || fail "transaction run should keep rows intact"
grep -q 'member_id' out/apply-after-none.txt && fail "no-transaction run should lose member_id"
grep -q '9001' out/apply-before-none.txt && fail "before, no transaction: ids should be renumbered"
echo "OK  one transaction: fails, rolls back; no transaction: member_id gone, ids renumbered"

npx ts-node src/string-demo.ts | tee out/string-demo.txt
npx ts-node src/id-type-demo.ts | tee out/id-type-demo.txt
grep -q "member_id: '5'" out/string-demo.txt || fail "raw row should hold a string"
grep -q 'after: id="9001"' out/id-type-demo.txt || fail "after fix the id should hydrate as a string"

LAB_FIX=1 npx typeorm-ts-node-commonjs migration:run -d src/data-source.ts >/dev/null
scripts/generate.sh after after-narrowing
[ "$(drops out/after-narrowing.sql)" = 0 ] || fail "after narrowing: expected 0 DROP COLUMN"
scripts/danger.sh out/after-narrowing.sql
echo "OK  after the narrowing migration: no destructive statements"
scripts/reset.sh  # leave the database in its pre-fix state
echo "ALL CHECKS PASSED"
