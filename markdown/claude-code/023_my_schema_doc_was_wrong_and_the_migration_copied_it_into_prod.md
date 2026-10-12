# My Schema Doc Was Wrong, and the Migration Copied It Into Prod

#### A context doc said every id was BIGINT. Claude Code believed it, Postgres allowed it, and the migration generator reported the mismatch for months, buried in 392 lines that nobody read

**By Tihomir Manushev**

*Oct 12, 2026 · 6 min read*

---

The dry run printed 392 statements. Fourteen of them dropped and re-added the id and foreign-key columns of three money tables in a mobile app's REST API: payout accounts, withdrawals and payout onboarding tokens. I hadn't asked for any of that. I was fixing a small item on a docs ticket.

The cause wasn't the ORM. It was a doc. The repo keeps hand-written context docs (architecture, business rules, endpoints, schema), and a session-start command loads them into every Claude Code session. That makes each doc an instruction. When one is wrong, the agent doesn't just misread it. It builds from it.

The project is private, so everything below comes from a small reconstruction lab: TypeORM 1.1.2, PostgreSQL 17, the same mistake on new tables. The two statement counts come from the real session.

---

### A wrong doc is an instruction

The schema doc was written as idealised SQL with prose around it, and it said every id in the system was `BIGINT`, the users table included:

```sql
CREATE TABLE members (
  id BIGSERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE
);
```

The real `id` column was `integer`. Months earlier, Claude Code wrote the hand-written migrations for the payout tables with that doc in its context, and it followed the doc: `BIGINT` primary keys, and `BIGINT` foreign keys pointing at `integer` keys. I can't prove the doc was the reason, but it was loaded, it said `BIGINT`, and the migration says `BIGINT`.

Postgres accepts a `bigint` column referencing an `integer` key, so nothing failed. The TypeORM entities declared no column type, so the ORM assumed `integer` everywhere. The database and the code had disagreed since the day the tables were created.

---

### Why nobody noticed

The `pg` driver returns `bigint` as a JavaScript string, because a 64-bit value doesn't fit in a `number`. That should have been loud. It wasn't:

```bash
$ npx ts-node src/string-demo.ts
raw row: { member_id: '5' }
entity:  { memberId: 5 }
```

A property with no declared type reflects as `Number`, and TypeORM calls `parseInt` on it when it reads a row. The wrong declaration hid the string. Raw queries did return strings, and the code handled that by sprinkling `Number()` wherever it read them. TypeScript saw `number` on both sides. The e2e suite builds its database from the same migrations, and the unit tests mock the repositories.

Only one tool compared the entities with the real schema, and it had been reporting the mismatch all along.

---

### The generator knew all along

`migration:generate` with `--dr` (dry run) prints the migration it would write without writing it. Run it against a fully migrated database and every statement is a disagreement between the code and the schema. In the lab, I keep only the `up()` SQL and filter it for statements that can lose data:

```bash
$ scripts/generate.sh before && scripts/danger.sh out/before.sql
before: 28 statements in up()
ALTER TABLE "cashout_accounts" DROP COLUMN "id"
ALTER TABLE "cashout_accounts" DROP COLUMN "member_id"
ALTER TABLE "cashouts" DROP COLUMN "id"
ALTER TABLE "cashouts" DROP COLUMN "member_id"
ALTER TABLE "cashouts" DROP COLUMN "account_id"
ALTER TABLE "cashouts" DROP COLUMN "debit_entry_id"
```

TypeORM expresses a type change as `DROP COLUMN` plus `ADD COLUMN`. Whoever generated a migration for some unrelated change would have picked these lines up with it.

The trap was set but never went off. The project runs migrations in one transaction, so on a table with rows the first `ADD ... NOT NULL` fails and everything rolls back: the deploy breaks and no data is lost. Run the same SQL by hand, statement by statement, and this is what's left:

```text
 amount_cents | status  | id | debit_entry_id
--------------+---------+----+----------------
         2500 | paid    |  1 |
          900 | pending |  2 |
```

Cashout 9001 is now cashout 1, `member_id` and `account_id` are gone, and the ledger link is NULL.

The rest of the 392 lines looked like noise: constraint names, a partial unique index and a CHECK constraint the ORM can't model. Running them loses no rows, but it does drop that index and that constraint without re-creating them.

---

### The fix that didn't fix

The obvious fix was to declare the type on every id and foreign key:

```typescript
@PrimaryGeneratedColumn({ type: "bigint" })
id: number;

@Column({ type: "bigint", name: "member_id" })
memberId: number;

@ManyToOne(() => Member)
@JoinColumn({ name: "member_id" })
member: Member;
```

Claude Code made the edit and first reported it as done. The after-diff disagreed. The primary keys came out clean, but three foreign keys still dropped (the real repo went from 392 statements to 360):

```bash
$ scripts/generate.sh after && scripts/danger.sh out/after.sql
after: 18 statements in up()
ALTER TABLE "cashout_accounts" DROP COLUMN "member_id"
ALTER TABLE "cashouts" DROP COLUMN "member_id"
ALTER TABLE "cashouts" DROP COLUMN "debit_entry_id"
```

So it read TypeORM's source and found this line in `RelationJoinColumnBuilder`:

```javascript
relationalColumn.type = referencedColumn.type; // also since types of relational column and join column must be equal we override user defined column type
```

A join column always takes the referenced key's type, and whatever you declare on it is ignored. `account_id` came out clean because the key it references is now `bigint`. The other three reference `integer` keys. This was the lesson of the session: the agent's confidence and the diff disagreed, and the diff was right.

There were three ways out. Widening the users and ledger keys would drag dozens of foreign keys along on the busiest tables. Removing the ORM relations would let the declared type stand, but it touches the money code to fix a generator problem. Narrowing the three columns to `integer` is a small forward-only migration, and it's safe because every value came from an `integer` key. After narrowing, the filter prints `no destructive statements`. `/code-review` on the docs commit flagged exactly these three leftover columns, and they became their own follow-up ticket.

One more gotcha: after the fix, `Cashout.id` hydrates as the string `"9001"`. The real code already ran ids through `Number()`, so nothing broke there.

---

### Turn it into a command

The dry run is a cheap drift detector once its output is quiet enough to read, so I made it a project slash command, `.claude/commands/drift-check.md`:

```markdown
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
```

Two lines in it come from mistakes. My first version had two separate `!` injections, which ran in parallel. The filter read the file before the generator had written it and reported "no destructive statements". The agent caught that contradiction itself. My first version also only said "do not edit files", so the agent proved its fix by altering the lab database and then reverting it. The second run on Claude Code 2.1.296 stayed read-only and produced the right three-row table.

The same distrust applies to audits. The ticket came from a drift audit three days old. Instead of executing it, Claude Code sent three read-only Explore subagents to re-check each claim against the code. Most held. One had already been fixed, one was half wrong, and one described a stale snippet. An audit is a snapshot, and it goes stale like the docs it checks.

---

### Conclusion

Once an agent reads your docs as context, documentation drift stops being a docs problem and becomes a code-generation problem. A wrong schema doc ended up as a wrong column type that survived for months, because the driver, the ORM, the types and the tests all smoothed it over. The generator saw it from the first day. Make its dry run quiet enough to read, and check the doc against the database the doc describes. When the agent says a fix worked, believe the diff.
