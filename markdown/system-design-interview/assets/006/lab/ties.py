"""What a tie means in SQL and what it means in a sorted set."""
import psycopg
import redis

DSN = "host=127.0.0.1 port=5462 dbname=postgres user=postgres password=demo"
KEY = "leaderboard:global"

TIE_SHAPE = """
SELECT count(*) AS players_sharing, score
FROM player_score
GROUP BY score
ORDER BY players_sharing DESC
LIMIT 1
"""
RANK_FORMS = """
SELECT player_id,
       rank()       OVER (ORDER BY score DESC) AS rank,
       dense_rank() OVER (ORDER BY score DESC) AS dense_rank,
       row_number() OVER (ORDER BY score DESC) AS row_number
FROM player_score
WHERE score >= %s
ORDER BY score DESC, player_id
LIMIT 6
"""


def main() -> None:
    pool = redis.Redis(host="127.0.0.1", port=6389, decode_responses=True)
    with psycopg.connect(DSN, autocommit=True) as conn:
        sharing, score = conn.execute(TIE_SHAPE).fetchone()
        print(f"most-shared score in postgres: {sharing:,} players "
              f"on score {score:,}")
        print()
        print("three SQL answers for the same six players:")
        print(f"{'player':<14}{'rank':>8}{'dense_rank':>12}{'row_number':>12}")
        for pid, rank, dense, row in conn.execute(RANK_FORMS, (249990,)):
            print(f"{'p' + str(pid):<14}{rank:>8}{dense:>12}{row:>12}")

    top_score = pool.zrevrange(KEY, 0, 0, withscores=True)[0][1]
    tied = pool.zrangebyscore(KEY, top_score, top_score)
    print()
    print(f"redis members on the top score {int(top_score):,}: {len(tied)}")
    for member in sorted(tied)[:6]:
        print(f"  {member:<14} ZREVRANK -> {pool.zrevrank(KEY, member)}")
    print()
    print("redis orders equal scores lexicographically by member, so rank")
    print("inside a tie group is alphabetical, not chronological or fair.")


if __name__ == "__main__":
    main()
