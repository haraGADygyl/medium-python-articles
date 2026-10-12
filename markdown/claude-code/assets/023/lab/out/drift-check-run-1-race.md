Three columns would be dropped and re-added. The `no destructive statements` line in the command header is wrong. I re-ran `scripts/danger.sh` and it printed:

```
ALTER TABLE "cashout_accounts" DROP COLUMN "member_id"
ALTER TABLE "cashouts" DROP COLUMN "member_id"
ALTER TABLE "cashouts" DROP COLUMN "debit_entry_id"
```

The generator also emits `ADD ... NOT NULL` for the first two, which fails on non-empty tables. The `ADD "debit_entry_id" integer` for `cashouts.debit_entry_id` is nullable and succeeds, but every value would be gone. `cashouts.account_id` is clean because `cashout_accounts.id` is `bigint`.

**Why they disagree.** All three columns are `@Column({ type: "bigint" })` in `src/after/`, but each is also the `@JoinColumn` of a `@ManyToOne`. TypeORM gives a join column the type of the referenced primary key. `members.id` and `ledger_entries.id` are `@PrimaryGeneratedColumn()`, which is `integer`. So the entity model says `integer`, the database says `bigint`, and TypeORM expresses "change the type" as DROP and ADD, not `ALTER TYPE`.

**Proof of the fix.** I temporarily ran `ALTER COLUMN ... TYPE integer` on the three columns via `psql`. The generator then emitted 12 statements and `danger.sh` printed `no destructive statements`. The remaining statements are only constraint and index churn. I then restored all three columns to `bigint`, and `git status` shows no file changes. This is the same change as `src/fix/1760000200000-NarrowCashoutForeignKeys.ts` (`LAB_FIX=1`), which I did not run.

| Column | Database type | Entity type | Cause | Proposed fix |
|---|---|---|---|---|
| `cashout_accounts.member_id` | bigint | integer (from `members.id`) | `type: "bigint"` on the join column is ignored | Narrow to `integer` with the forward-only `NarrowCashoutForeignKeys` migration; drop the misleading `type: "bigint"` from the entities. |
| `cashouts.member_id` | bigint | integer (from `members.id`) | same | same |
| `cashouts.debit_entry_id` | bigint | integer (from `ledger_entries.id`) | same, referenced PK is `ledger_entries.id` | same |

The narrowing is safe for the current data. All values are small (5, 3, 1, 2), but the migration fails if a larger value ever appears. The alternative is to widen `members.id` and `ledger_entries.id` to `bigint`. That rewrites two referenced primary keys, so I'd pick narrowing.

I generated `out/drift-check.sql` and `out/trial-fix.sql` while checking. `git status` shows no other changes (`?? ./` only).
