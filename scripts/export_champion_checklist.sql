COPY (
    SELECT
        s.year AS season,
        t.name AS team,
        t.slug AS team_slug,
        r.team_id,
        t.is_d1,
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
        r.sor_rank,
        r.net_rank,
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

    FROM core_teamseasonratings r
    JOIN core_season s
        ON r.season_id = s.id
    JOIN core_team t
        ON r.team_id = t.id
    LEFT JOIN core_teamseasonmetrics m
        ON r.team_id = m.team_id
       AND r.season_id = m.season_id
       AND m.is_pre_tournament = TRUE

    WHERE r.is_pre_tournament = TRUE
      AND s.year BETWEEN 2005 AND 2026
      AND s.year <> 2020
      AND r.games_played > 0

    ORDER BY s.year, t.name
) TO STDOUT WITH (FORMAT CSV, HEADER TRUE);
