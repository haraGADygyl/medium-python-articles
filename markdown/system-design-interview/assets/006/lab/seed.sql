DROP TABLE IF EXISTS player_score;
CREATE TABLE player_score (
    player_id bigint PRIMARY KEY,
    handle    text   NOT NULL,
    score     int    NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO player_score (player_id, handle, score)
SELECT g,
       'p' || g,
       (random() * 250000)::int
FROM generate_series(1, 50000000) g;
CREATE INDEX player_score_desc ON player_score (score DESC, player_id);
ANALYZE player_score;
