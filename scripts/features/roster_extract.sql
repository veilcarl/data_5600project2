-- Roster feature extracts (read-only). Run from the repo root:
--   PGOPTIONS='-c default_transaction_read_only=on' psql -d macfax -f scripts/features/roster_extract.sql
-- Writes three CSVs to data/raw/ (gitignored); scripts/features/roster.py builds data/interim/roster.csv.
--
-- Scope: D1-vs-D1 games with status 'final', excluding canceled 0-0 games, seasons with
-- player-game rows (2005-2026; 2005-2014 from the Task 12 backfill). D1 = TeamSeasonMembership.is_d1 for that season (not Team.is_d1), so a
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
  AND g.season_year BETWEEN 2005 AND 2026
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
  AND g.season_year BETWEEN 2005 AND 2026
ORDER BY g.season_year, g.game_date, g.id, p.player_id;

-- Players ESPN left out of its 2022-23 / 2023-24 boxes, filled from ncaa.com box scores
-- (core_missingplayergamestats, source 'ncaa'). player_id: core_player link where set ('core'); otherwise the
-- one player with exactly this display name and player-game rows for the same team in Y-1 or Y+1 ('adjacent');
-- NULL when there is none or more than one ('unlinked').
\o data/raw/roster_ncaa_filled.csv
WITH m AS (
    SELECT m.id, g.season_year AS season, g.id AS game_id, g.game_date,
           (g.game_date <= s.selection_sunday_date) AS pre_cutoff,
           g.home_team_id, g.away_team_id, m.team_id, m.name, m.player_id AS core_player_id,
           m.minutes, m.points
    FROM core_missingplayergamestats m
    JOIN core_game g ON g.id = m.game_id
    JOIN core_season s ON s.year = g.season_year
    JOIN core_teamseasonmembership mh ON mh.team_id = g.home_team_id AND mh.season_id = s.id AND mh.is_d1
    JOIN core_teamseasonmembership ma ON ma.team_id = g.away_team_id AND ma.season_id = s.id AND ma.is_d1
    WHERE m.source = 'ncaa'
      AND g.status = 'final'
      AND NOT (g.home_score = 0 AND g.away_score = 0)
      AND g.season_year BETWEEN 2005 AND 2026
), adj AS (
    SELECT m.id, min(pl.id) AS player_id, count(DISTINCT pl.id) AS n
    FROM m
    JOIN core_player pl ON pl.display_name = m.name
    WHERE m.core_player_id IS NULL
      AND EXISTS (SELECT 1 FROM core_playergamestats p JOIN core_game g2 ON g2.id = p.game_id
                  WHERE p.player_id = pl.id AND p.team_id = m.team_id
                    AND g2.season_year IN (m.season - 1, m.season + 1))
    GROUP BY m.id
)
SELECT m.season, m.game_id, m.game_date, m.pre_cutoff, m.home_team_id, m.away_team_id,
       COALESCE(m.core_player_id, CASE WHEN adj.n = 1 THEN adj.player_id END) AS player_id,
       m.team_id, m.name, m.minutes, m.points,
       CASE WHEN m.core_player_id IS NOT NULL THEN 'core'
            WHEN adj.n = 1 THEN 'adjacent'
            ELSE 'unlinked' END AS link
FROM m
LEFT JOIN adj ON adj.id = m.id
ORDER BY m.season, m.game_date, m.game_id, m.team_id, m.name;

\o
