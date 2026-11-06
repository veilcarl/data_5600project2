-- Roster feature extracts (read-only). Run from the repo root:
--   PGOPTIONS='-c default_transaction_read_only=on' psql -d macfax -f scripts/features/roster_extract.sql
-- Writes two CSVs to data/raw/ (gitignored); scripts/features/roster.py builds data/interim/roster.csv.
--
-- Scope: D1-vs-D1 games with status 'final', excluding canceled 0-0 games, seasons with
-- player-game rows (2015+). ALL games of each season are extracted (the Y-1 lookback uses
-- full seasons); pre_cutoff flags game_date <= Season.selection_sunday_date.
-- periods: raw ESPN status.period for 2005-2025, except 2018 games that say period 4 with a
-- plain 'Final' status (regulation); period_count for 2026+. NULL when unknown or < 2.

\pset format csv
\pset footer off

\o data/raw/roster_team_games.csv
SELECT g.season_year AS season,
       g.id AS game_id,
       g.game_date,
       (g.game_date <= s.selection_sunday_date) AS pre_cutoff,
       side.team_id,
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
       END AS periods
FROM core_game g
JOIN core_season s ON s.year = g.season_year
JOIN core_team h ON h.id = g.home_team_id AND h.is_d1
JOIN core_team a ON a.id = g.away_team_id AND a.is_d1
CROSS JOIN LATERAL (VALUES (g.home_team_id), (g.away_team_id)) AS side(team_id)
WHERE g.status = 'final'
  AND NOT (g.home_score = 0 AND g.away_score = 0)
  AND g.season_year >= 2015
ORDER BY g.season_year, g.game_date, g.id, side.team_id;

\o data/raw/roster_player_games.csv
SELECT g.season_year AS season,
       g.id AS game_id,
       g.game_date,
       (g.game_date <= s.selection_sunday_date) AS pre_cutoff,
       g.home_team_id,
       g.away_team_id,
       p.player_id,
       p.team_id,
       p.minutes,
       p.points
FROM core_playergamestats p
JOIN core_game g ON g.id = p.game_id
JOIN core_season s ON s.year = g.season_year
JOIN core_team h ON h.id = g.home_team_id AND h.is_d1
JOIN core_team a ON a.id = g.away_team_id AND a.is_d1
WHERE g.status = 'final'
  AND NOT (g.home_score = 0 AND g.away_score = 0)
  AND g.season_year >= 2015
ORDER BY g.season_year, g.game_date, g.id, p.player_id;

\o
