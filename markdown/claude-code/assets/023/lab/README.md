# Lab: a wrong schema doc, copied into a migration

A fresh, generic reconstruction for article 023. Two hand-written migrations
build a small cashout schema. The second followed `docs/schema.md` ("every key
is BIGSERIAL"), which was wrong: `members.id` and `ledger_entries.id` are
`integer`. Postgres accepts a `bigint` foreign key to an `integer` key, so
nothing fails until TypeORM's migration generator compares entities with the
database.

TypeORM 1.1.2, pg 8.23.1, PostgreSQL 17 in Docker on port 55432.

```bash
npm ci
./verify.sh          # rebuilds everything, checks every number below
```

| Entities | `DROP COLUMN` in generated `up()` | File |
| --- | --- | --- |
| `src/before/`: no `type` on any id | 6 (2 primary keys, 4 FKs) | `out/before.sql` |
| `src/after/`: `type: "bigint"` on all of them | 3 (FKs to `integer` keys) | `out/after.sql` |
| `src/no-relation/`: cashout FKs without `@ManyToOne` | 1 (the untouched `cashout_accounts.member_id`) | `out/no-relation.sql` |
| `src/after/` + `src/fix/` narrowing migration applied | 0 | `out/after-narrowing.sql` |

Why `type: "bigint"` on a join column changes nothing:
`node_modules/typeorm/metadata-builder/RelationJoinColumnBuilder.js:208`
sets `relationalColumn.type = referencedColumn.type`, with the comment
"also since types of relational column and join column must be equal we
override user defined column type".

What the generated migration does to rows (`scripts/apply-generated.sh`, on a
throwaway copy):

- **In one transaction** (TypeORM's default `transaction: "all"`): re-adding a
  `NOT NULL` column to a table with rows fails, everything rolls back. The
  deploy breaks; no data is lost. `out/apply-after-all.txt`
- **Without a transaction**: `member_id` disappears, `debit_entry_id` comes back
  NULL, and before the fix the ids are renumbered (9001 becomes 1).
  `out/apply-after-none.txt`, `out/apply-before-none.txt`

Why nobody noticed (`src/string-demo.ts`, `src/id-type-demo.ts`): `pg` returns
`bigint` as a string (`'5'`), but an entity property with no `type` reflects
as `Number`, and TypeORM `parseInt`s it on read. The wrong declaration hid the
string. After the fix, `Cashout.id` hydrates as `"9001"`.

`.claude/commands/drift-check.md` is the slash command from the article.
`out/drift-check-run-1-race.md` is its first run, where two `!` injections
ran in parallel and the agent proved its fix by altering the database (then
reverted it). `out/drift-check-run-2.md` is the read-only version.
