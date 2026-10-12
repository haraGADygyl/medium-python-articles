# Schema

Every primary key is `BIGSERIAL`, and every foreign key that points at one
is `BIGINT` as well.

```sql
CREATE TABLE members (
  id BIGSERIAL PRIMARY KEY,
  email TEXT NOT NULL UNIQUE
);

CREATE TABLE ledger_entries (
  id BIGSERIAL PRIMARY KEY,
  member_id BIGINT NOT NULL REFERENCES members (id),
  delta_cents INTEGER NOT NULL
);
```
