-- Base team-season table v2 (read-only). Run from the repo root:
--   PGOPTIONS='-c default_transaction_read_only=on' psql -d macfax -f scripts/export_base_v2.sql > data/interim/base.csv
-- Derived from export_champion_checklist.sql (v1, unchanged). Differences:
--   * rows: team-seasons D1 that season (TeamSeasonMembership.is_d1, not Team.is_d1) with at least one D1-vs-D1
--     final game on or before Selection Sunday, 0-0 excluded (the team_games.csv rule), 2005-2026 except 2020;
--     pre-tournament ratings and metrics are LEFT JOINed, so a missing rating row shows as NULLs, not a lost row
--   * dropped: net_rank, sor_rank; Team.is_d1 replaced by membership is_reclassifying
--   * added: conference (Conference.code from the pre-tournament TeamSeasonMetrics row), is_reclassifying
COPY (
    SELECT
        s.year AS season,
        t.name AS team,
        t.slug AS team_slug,
        r.team_id,
        mem.is_reclassifying,
        c.code AS conference,
        (r.tournament_seed IS NOT NULL) AS made_tournament,
        r.tournament_seed,
        r.tournament_region,
        r.tournament_finish,
        CASE WHEN r.tournament_finish = 'Champ'
             THEN 1 ELSE 0 END AS champion,

        r.games_played,
        r.wins,
        r.losses,
        CASE WHEN r.games_played > 0
             THEN r.wins::float / r.games_played
             END AS win_pct,

        r.adj_o,
        r.adj_d,
        r.adj_em,
        r.adj_tempo,
        r.rank_adj_o,
        r.rank_adj_d,
        r.rank_adj_em,

        r.adj_efg_pct,
        r.adj_opp_efg_pct,
        r.adj_efg_margin,
        r.adj_tov_pct,
        r.adj_opp_tov_pct,
        r.adj_tov_edge,
        r.adj_orb_pct,
        r.adj_drb_pct,
        r.adj_reb_edge,
        r.adj_ftr,
        r.adj_opp_ftr,
        r.adj_ftr_margin,

        r.ffi_adj,
        r.wab,
        r.sos_rank,
        r.ap_poll_week6,

        m.total_fg3m,
        m.total_fg3a,
        CASE WHEN m.total_fg3a > 0
             THEN m.total_fg3m::float / m.total_fg3a
             END AS three_pt_pct,

        m.total_ftm,
        m.total_fta,
        CASE WHEN m.total_fta > 0
             THEN m.total_ftm::float / m.total_fta
             END AS ft_pct

    FROM core_teamseasonmembership mem
    JOIN core_season s
        ON mem.season_id = s.id
    JOIN core_team t
        ON mem.team_id = t.id
    LEFT JOIN core_teamseasonratings r
        ON r.team_id = mem.team_id
       AND r.season_id = mem.season_id
       AND r.is_pre_tournament = TRUE
    LEFT JOIN core_teamseasonmetrics m
        ON m.team_id = mem.team_id
       AND m.season_id = mem.season_id
       AND m.is_pre_tournament = TRUE
    LEFT JOIN core_conference c
        ON c.id = m.conference_id

    WHERE mem.is_d1
      AND s.year BETWEEN 2005 AND 2026
      AND s.year <> 2020
      AND EXISTS (
          SELECT 1
          FROM core_game g
          JOIN core_teamseasonmembership mo
            ON mo.season_id = s.id
           AND mo.is_d1
           AND mo.team_id = CASE WHEN g.home_team_id = mem.team_id THEN g.away_team_id ELSE g.home_team_id END
          WHERE g.season_year = s.year
            AND mem.team_id IN (g.home_team_id, g.away_team_id)
            AND g.status = 'final'
            AND NOT (g.home_score = 0 AND g.away_score = 0)
            AND g.game_date <= s.selection_sunday_date
      )

    ORDER BY s.year, t.name
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);
