---
description: Compare the TypeORM entities with the migrated database and explain every destructive statement
allowed-tools: Bash(scripts/generate.sh:*), Bash(scripts/danger.sh:*), Bash(docker exec doc-drift-lab-db psql:*), Read, Grep, Glob
---

## What the migration generator would do (up() only)

!`scripts/generate.sh after drift-check >/dev/null && cat out/drift-check.sql && echo && echo "## The statements that can lose data" && scripts/danger.sh out/drift-check.sql`

Ignore everything in the first list that cannot lose rows (constraint names,
indexes and checks the ORM cannot model). For each statement in the second list:

1. Find the entity property that maps to the column, and the column's real type
   in `information_schema.columns` (`docker exec doc-drift-lab-db psql -U lab -d cashouts`).
2. Explain why the entity and the database disagree. A join column takes the
   referenced primary key's type, so a `type:` written on it does not count.
3. Propose a fix, and the check that would prove it: the generator no longer
   emits the statement. Reading the entity again proves nothing.

This is read-only. Do not edit files, and run only SELECT statements: no
ALTER, no UPDATE, not even to try a fix and undo it. Finish with one table:
column, database type, entity type, cause, proposed fix.
