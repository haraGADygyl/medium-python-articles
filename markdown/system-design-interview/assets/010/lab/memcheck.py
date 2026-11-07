"""MEMORY USAGE vs what Redis actually allocates for count-min sketches."""
from common import connect

r = connect()
r.flushall()

for width in (2_000, 10_000, 20_000, 50_000, 100_000):
    before = r.info("memory")["used_memory"]

    for i in range(36):
        r.execute_command("CMS.INITBYDIM", f"m:{width}:{i}", width, 7)

    after = r.info("memory")["used_memory"]
    print(f"width {width:,} x depth 7: MEMORY USAGE {r.memory_usage(f'm:{width}:0', samples=0):,} B, "
          f"used_memory per sketch {(after - before) / 36:,.0f} B "
          f"({(after - before) / 36 / (width * 7):.1f} B per counter)")
