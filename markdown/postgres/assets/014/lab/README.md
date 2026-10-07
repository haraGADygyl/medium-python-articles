# Lab for 014 — temporal keys in PostgreSQL 18

PostgreSQL 18.0 in Docker, `shared_buffers=1GB`, `jit=off`, port 55418:

    docker run -d --name pg18-temporal -e POSTGRES_PASSWORD=lab -p 55418:5432 postgres:18 \
      -c shared_buffers=1GB -c jit=off -c max_connections=200

| File | What it measures |
| --- | --- |
| `article_blocks.sql` | Every SQL block in the article, in order, with the errors it expects |
| `race.py` | 24 workers × 250 check-then-insert attempts: READ COMMITTED, SERIALIZABLE, WITHOUT OVERLAPS (`python3 race.py 3`) |
| `schema.sql`, `bench_setup.sql` | 20,000 vans, 40,000 policies, 1M staged rentals (scripts expect `/schema.sql` inside the container) |
| `bench_insert.sh` | Load time, WAL and index size for the five schemas, 3 runs each |
| `after_load.sql` | ADD PRIMARY KEY / ADD FOREIGN KEY after the load, index sizes, lookup plans |
| `fkval.sql` | Temporal FK: one-step ADD (20.6 s) vs NOT VALID + VALIDATE (0.33 s) |
