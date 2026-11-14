-- Roster feature extracts (read-only). Run from the repo root:
--   PGOPTIONS='-c default_transaction_read_only=on' psql -d macfax -f scripts/features/roster_extract.sql
-- Writes two CSVs to data/raw/ (gitignored); scripts/features/roster.py builds data/interim/roster.csv.
--
-- Scope: D1-vs-D1 games with status 'final', excluding canceled 0-0 games, seasons with
-- player-game rows (2015+). D1 = TeamSeasonMembership.is_d1 for that season (not Team.is_d1), so a
-- player's prior team is his last D1-that-season team. ALL games of each season are extracted (the Y-1
-- lookback uses full seasons); pre_cutoff flags game_date <= Season.selection_sunday_date.
-- periods: Game.period_count (every season); NULL when unknown or < 2.

\pset format csv
\pset footer off

\o data/raw/roster_team_games.csv
SELECT g.season_year AS season,
       g.id AS game_id,
       g.game_date,
       (g.game_date <= s.selection_sunday_date) AS pre_cutoff,
       side.team_id,
       CASE WHEN g.period_count >= 2 THEN g.period_count END AS periods
FROM core_game g
JOIN core_season s ON s.year = g.season_year
JOIN core_teamseasonmembership mh ON mh.team_id = g.home_team_id AND mh.season_id = s.id AND mh.is_d1
JOIN core_teamseasonmembership ma ON ma.team_id = g.away_team_id AND ma.season_id = s.id AND ma.is_d1
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
JOIN core_teamseasonmembership mh ON mh.team_id = g.home_team_id AND mh.season_id = s.id AND mh.is_d1
JOIN core_teamseasonmembership ma ON ma.team_id = g.away_team_id AND ma.season_id = s.id AND ma.is_d1
WHERE g.status = 'final'
  AND NOT (g.home_score = 0 AND g.away_score = 0)
  AND g.season_year >= 2015
ORDER BY g.season_year, g.game_date, g.id, p.player_id;

\o
