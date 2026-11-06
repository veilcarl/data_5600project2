-- NCAA tournament outcome extracts (read-only). Run from the repo root:
--   PGOPTIONS='-c default_transaction_read_only=on' psql -d macfax -f scripts/features/outcome_extract.sql
-- Writes data/raw/outcome_games.csv and data/raw/outcome_seeds.csv (gitignored);
-- scripts/features/outcome.py classifies the games and builds data/interim/outcome.csv.
--
-- Candidate games: 2005-2025 ESPN raw season.type = 3 (all postseason: NCAA, NIT, CBI, ...);
-- 2026 ncaa.com raw championshipId = 6393 (the NCAA tournament). 2020 has no tournament.
-- start_utc: ESPN raw event date (2005-2025) or ncaa.com startTimeEpoch (2026). game_date is a UTC
-- date for evening games, so outcome.py uses start_utc for any date logic.

\pset format csv
\pset footer off

\o data/raw/outcome_games.csv
SELECT g.season_year AS season,
       g.id AS game_id,
       g.game_date,
       CASE WHEN g.season_year <= 2025 THEN (g.raw_json::jsonb -> '_raw' ->> 'date')
            ELSE to_char(to_timestamp((g.raw_json::jsonb -> '_raw' ->> 'startTimeEpoch')::bigint) AT TIME ZONE 'UTC',
                         'YYYY-MM-DD"T"HH24:MI"Z"')
       END AS start_utc,
       s.selection_sunday_date,
       g.raw_json::jsonb -> '_raw' -> 'competitions' -> 0 -> 'notes' -> 0 ->> 'headline' AS headline,
       NULLIF(g.raw_json::jsonb -> '_raw' ->> 'championshipId', '') AS championship_id,
       NULLIF(g.raw_json::jsonb -> '_raw' ->> 'bracketRound', '') AS bracket_round,
       g.home_team_id,
       g.away_team_id,
       g.home_score,
       g.away_score
FROM core_game g
JOIN core_season s ON s.year = g.season_year
WHERE g.status = 'final'
  AND g.season_year BETWEEN 2005 AND 2026
  AND g.season_year <> 2020
  AND ((g.season_year <= 2025 AND g.raw_json::jsonb -> '_raw' -> 'season' ->> 'type' = '3')
       OR (g.season_year = 2026 AND g.raw_json::jsonb -> '_raw' ->> 'championshipId' = '6393'))
ORDER BY g.season_year, start_utc, g.id;

\o data/raw/outcome_seeds.csv
SELECT s.year AS season,
       r.team_id,
       t.name AS team_name,
       r.tournament_seed,
       r.tournament_finish
FROM core_teamseasonratings r
JOIN core_season s ON s.id = r.season_id
JOIN core_team t ON t.id = r.team_id
WHERE NOT r.is_pre_tournament
  AND s.year BETWEEN 2005 AND 2026
  AND (r.tournament_seed IS NOT NULL OR r.tournament_finish IS NOT NULL)
ORDER BY s.year, r.team_id;

\o data/raw/outcome_teams.csv
SELECT id AS team_id, name AS team_name FROM core_team ORDER BY id;

\o
