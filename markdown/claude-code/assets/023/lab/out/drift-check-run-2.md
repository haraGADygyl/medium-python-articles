Three columns drift, and they all have the same cause. The three columns are `bigint` in the database, but the entities resolve them to `integer`. I didn't run the generator again, because the statements you pasted already show the result. I ran only SELECTs.

**What the database has**

| Table | Column | Type |
|---|---|---|
| `members` | `id` | integer |
| `ledger_entries` | `id` | integer |
| `cashout_accounts` | `id` | bigint |
| `cashout_accounts` | `member_id` | bigint |
| `cashouts` | `member_id` | bigint |
| `cashouts` | `debit_entry_id` | bigint, nullable |

**Why they disagree.** `src/after/member.entity.ts` and `src/after/ledger-entry.entity.ts` use a bare `@PrimaryGeneratedColumn()`, which TypeORM maps to `integer`. The `@ManyToOne` and `@JoinColumn` on the three columns point at those keys. TypeORM takes a join column's type from the referenced primary key, so it ignores `@Column({ type: "bigint" })` on the same field. It wants `integer`, finds `bigint`, and emits DROP COLUMN followed by ADD COLUMN, which loses the data. `cashouts.account_id` is clean because `CashoutAccount.id` really is `bigint`.

`docs/schema.md` says every key is `BIGSERIAL`. That is stale, because `members.id` and `ledger_entries.id` are `integer` in the database.

**The data would fit either way.** The largest values are 5 for the member columns and 2 for `debit_entry_id`, so narrowing to `integer` would lose nothing today.

**Fix options**
- **Narrow the foreign keys (recommended).** `src/fix/1760000200000-NarrowCashoutForeignKeys.ts` already does this with `ALTER COLUMN ... TYPE integer`. It matches the real key types, so it's the smaller change. It is forward-only, and it fails if a value above 2^31 ever appears.
- **Widen the primary keys.** Change `Member.id` and `LedgerEntry.id` to `{ type: "bigint" }` and write a migration that alters the primary keys and the foreign keys that reference them. This matches `docs/schema.md`, but it is heavier. The ids would also hydrate as strings instead of numbers, and every id comparison in the code would need checking.

**Check that proves it.** After applying the fix, run:

```
LAB_FIX=1 LAB_ENTITIES=after scripts/generate.sh after after-narrowing
grep -c 'DROP COLUMN' out/after-narrowing.sql   # expect 0
```

`verify.sh` runs this same check. Reading the entity again proves nothing.

| Column | Database type | Entity type | Cause | Proposed fix |
|---|---|---|---|---|
| `cashout_accounts.member_id` | bigint | integer (from `members.id`) | The `type: "bigint"` is ignored because the join column takes the referenced key's type. | `ALTER COLUMN member_id TYPE integer`, then confirm 0 DROP COLUMN. |
| `cashouts.member_id` | bigint | integer (from `members.id`) | Same as above. | `ALTER COLUMN member_id TYPE integer`, then the same check. |
| `cashouts.debit_entry_id` | bigint, nullable | integer (from `ledger_entries.id`) | Same as above, with `LedgerEntry.id` as the referenced key. | `ALTER COLUMN debit_entry_id TYPE integer`, then the same check. |
