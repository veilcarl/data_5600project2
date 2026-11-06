-- Team-game feature extract (read-only). Run from the repo root:
--   PGOPTIONS='-c default_transaction_read_only=on' psql -d macfax -f scripts/features/team_games_extract.sql
-- Writes data/raw/team_games_rows.csv (gitignored); scripts/features/team_games.py builds data/interim/team_games.csv.
--
-- One row per team per game: D1-vs-D1, status 'final', canceled 0-0 games excluded, pre-cutoff only
-- (game_date <= Season.selection_sunday_date), seasons 2005-2026 except 2020.
-- start_utc: ESPN raw event date (2005-2025) or ncaa.com startTimeEpoch (2026), for ordering by game time.
-- box_home_away: the team's own box row (H/A/N; NULL if the row is missing).
-- periods: raw status.period 2005-2025 (2018 games saying period 4 with a plain 'Final' status are
--   regulation); period_count 2026. NULL when unknown or < 2.
-- opp_rank_adj_em: opponent's pre-tournament rank (TeamSeasonRatings is_pre_tournament = true).

\pset format csv
\pset footer off

\o data/raw/team_games_rows.csv
SELECT g.season_year AS season,
       g.id AS game_id,
       g.game_date,
       CASE WHEN g.season_year <= 2025 THEN (g.raw_json::jsonb -> '_raw' ->> 'date')
            ELSE to_char(to_timestamp(NULLIF(g.raw_json::jsonb -> '_raw' ->> 'startTimeEpoch', '')::bigint)
                         AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI"Z"')
       END AS start_utc,
       side.team_id,
       side.opp_id,
       (side.team_id = g.home_team_id) AS is_game_home,
       g.neutral_site AS game_neutral,
       tb.home_away AS box_home_away,
       CASE WHEN side.team_id = g.home_team_id THEN g.home_score ELSE g.away_score END AS pts,
       CASE WHEN side.team_id = g.home_team_id THEN g.away_score ELSE g.home_score END AS opp_pts,
       tb.fga, tb.fg3a,
       ob.fga AS opp_fga, ob.fg3a AS opp_fg3a,
       CASE
         WHEN g.season_year <= 2025 THEN
           CASE
             WHEN (g.raw_json::jsonb -> '_raw' -> 'status' ->> 'period') !~ '^[0-9]+$' THEN NULL
             WHEN g.season_year = 2018
                  AND (g.raw_json::jsonb -> '_raw' -> 'status' ->> 'period')::int = 4
                  AND (g.raw_json::jsonb -> '_raw' -> 'status' -> 'type' ->> 'detail') = 'Final' THEN 2
             WHEN (g.raw_json::jsonb -> '_raw' -> 'status' ->> 'period')::int >= 2
               THEN (g.raw_json::jsonb -> '_raw' -> 'status' ->> 'period')::int
           END
         ELSE CASE WHEN g.period_count >= 2 THEN g.period_count END
       END AS periods,
       orr.rank_adj_em AS opp_rank_adj_em
FROM core_game g
JOIN core_season s ON s.year = g.season_year
JOIN core_team h ON h.id = g.home_team_id AND h.is_d1
JOIN core_team a ON a.id = g.away_team_id AND a.is_d1
CROSS JOIN LATERAL (VALUES (g.home_team_id, g.away_team_id), (g.away_team_id, g.home_team_id)) AS side(team_id, opp_id)
LEFT JOIN core_teamgamestats tb ON tb.game_id = g.id AND tb.team_id = side.team_id
LEFT JOIN core_teamgamestats ob ON ob.game_id = g.id AND ob.team_id = side.opp_id
LEFT JOIN core_teamseasonratings orr ON orr.team_id = side.opp_id AND orr.season_id = s.id AND orr.is_pre_tournament
WHERE g.status = 'final'
  AND NOT (g.home_score = 0 AND g.away_score = 0)
  AND g.game_date <= s.selection_sunday_date
  AND g.season_year BETWEEN 2005 AND 2026
  AND g.season_year <> 2020
ORDER BY g.season_year, side.team_id, start_utc, g.id;

\o
