"""Roster continuity features: one row per D1 team-season with player-game data.

Inputs (run scripts/features/roster_extract.sql first, from the repo root):
  data/raw/roster_player_games.csv   player-game rows, D1-vs-D1 final games, 0-0 games excluded
  data/raw/roster_team_games.csv     one row per team-game, with periods (OT) for minutes closure
  data/reference/player_id_aliases.csv   core_player ids, old -> new (ESPN re-issued ids)

Output:
  data/interim/roster.csv

Definitions (season Y, team T, "pre" = game_date <= Selection Sunday):
  prior team    p's most recent D1 team in Y-1 (latest game), else in Y-2 (sit-out / redshirt years)
  category      same-team returner (prior == T), transfer (prior != T), newcomer (no D1 rows in Y-1 or Y-2)
  team_min_obs  sum of T's pre-cutoff player minutes
  shares        category minutes / team_min_obs
  ret_prior_min_pct   share of T's Y-1 player minutes (all Y-1 games) by players who appear for T in Y pre-cutoff
  ret_same_pts_pct    share of T's pre-cutoff player points scored by same-team returners
  exp_prior_seasons   minutes-weighted mean count of seasons before Y with D1 game rows (any team)
  exp_censored        True when Y - first season with player data < 4
  min_closure_pct     share of T's pre-cutoff games (with a known period count) whose player minutes are
                      within +-5 of 200 + 25 per OT period; roster_quality ok >= 0.90, partial >= 0.50, else poor
Seasons whose Y-1 has no player data get NULL continuity and experience columns. Unknown is NULL, never 0.

Run:  .venv/bin/python scripts/features/roster.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PG_PATH = ROOT / "data/raw/roster_player_games.csv"
TG_PATH = ROOT / "data/raw/roster_team_games.csv"
ALIAS_PATH = ROOT / "data/reference/player_id_aliases.csv"
OUT_PATH = ROOT / "data/interim/roster.csv"

LAST_SEASON = 2026  # dataset scope ends with 2025-26; later in-progress seasons are not output
CLOSURE_TOL = 5.0
QUALITY_OK, QUALITY_PARTIAL = 0.90, 0.50


def _flag(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["t", "true"])


def load():
    pg = pd.read_csv(PG_PATH, dtype={"team_id": "Int64"})
    tg = pd.read_csv(TG_PATH, dtype={"periods": "Int64"})
    aliases = pd.read_csv(ALIAS_PATH)
    pg["pre_cutoff"] = _flag(pg["pre_cutoff"])
    tg["pre_cutoff"] = _flag(tg["pre_cutoff"])
    pg["game_date"] = pd.to_datetime(pg["game_date"])
    return pg, tg, aliases


def remap_ids(pg: pd.DataFrame, aliases: pd.DataFrame, stats: dict) -> pd.DataFrame:
    amap = dict(zip(aliases["old_player_id"], aliases["new_player_id"]))
    stats["alias_rows"] = len(amap)
    stats["alias_old_ids_with_rows"] = int(pg["player_id"].isin(amap.keys()).groupby(pg["player_id"]).any().sum())
    stats["alias_player_game_rows_remapped"] = int(pg["player_id"].isin(amap.keys()).sum())
    stats["alias_new_ids_with_rows"] = int(pd.Series(list(amap.values())).isin(pg["player_id"]).sum())
    pg = pg.copy()
    pg["player_id"] = pg["player_id"].map(lambda p: amap.get(p, p))
    dup = pg.duplicated(["game_id", "player_id"], keep="first")
    stats["duplicate_rows_after_remap"] = int(dup.sum())
    return pg[~dup]


def assign_null_teams(pg: pd.DataFrame, stats: dict) -> pd.DataFrame:
    """Rows with no team: use the player's only team that season, if that team played in the game."""
    known = pg[pg["team_id"].notna()]
    teams = known.groupby(["season", "player_id"])["team_id"].agg(lambda s: set(s))
    null = pg["team_id"].isna()
    stats["null_team_rows"] = int(null.sum())
    fill = []
    for idx, row in pg[null].iterrows():
        cand = teams.get((row["season"], row["player_id"]), set())
        t = next(iter(cand)) if len(cand) == 1 else None
        fill.append(t if t in (row["home_team_id"], row["away_team_id"]) else None)
    pg = pg.copy()
    pg.loc[null, "team_id"] = pd.array(fill, dtype="Int64")
    stats["null_team_rows_assigned"] = int(pg.loc[null, "team_id"].notna().sum())
    stats["null_team_rows_dropped"] = int(pg.loc[null, "team_id"].isna().sum())
    pg = pg[pg["team_id"].notna()].copy()
    bad = ~((pg["team_id"] == pg["home_team_id"]) | (pg["team_id"] == pg["away_team_id"]))
    stats["rows_team_not_in_game_dropped"] = int(bad.sum())
    pg = pg[~bad].copy()
    pg["team_id"] = pg["team_id"].astype("int64")
    return pg


def closure(pg: pd.DataFrame, tg: pd.DataFrame, stats: dict) -> pd.DataFrame:
    pre_tg = tg[tg["pre_cutoff"]].copy()
    mins = pg[pg["pre_cutoff"]].groupby(["game_id", "team_id"])["minutes"].sum()
    pre_tg["mins"] = [mins.get((g, t), 0.0) for g, t in zip(pre_tg["game_id"], pre_tg["team_id"])]
    known = pre_tg["periods"].notna()
    stats["closure_games_unknown_periods"] = int((~known).sum())
    pre_tg = pre_tg[known].copy()
    expected = 200 + 25 * (pre_tg["periods"].astype(int) - 2)
    pre_tg["within"] = (pre_tg["mins"] - expected).abs() <= CLOSURE_TOL
    out = pre_tg.groupby(["season", "team_id"])["within"].mean().rename("min_closure_pct").reset_index()
    return out


def build():
    stats = {}
    pg, tg, aliases = load()
    stats["player_game_rows_in"] = len(pg)
    pg = remap_ids(pg, aliases, stats)
    pg = assign_null_teams(pg, stats)
    first_season = int(pg["season"].min())
    data_seasons = set(pg["season"].unique())

    # Player history: seasons with D1 rows; most recent D1 team in each season (latest game, all games).
    seasons_by_player = pg.groupby("player_id")["season"].agg(lambda s: sorted(set(s)))
    # (sort + drop_duplicates rather than groupby().tail(1), which segfaults in pandas 3.1 / Python 3.14)
    last = pg.sort_values(["game_date", "game_id"]).drop_duplicates(["player_id", "season"], keep="last")
    last_team = dict(zip(zip(last["player_id"], last["season"]), last["team_id"]))

    pre = pg[pg["pre_cutoff"]]
    ps = (pre.groupby(["season", "team_id", "player_id"], as_index=False)
             .agg(minutes=("minutes", "sum"), points=("points", "sum")))

    def category(p, y, t):
        prior = last_team.get((p, y - 1), last_team.get((p, y - 2)))
        if prior is None:
            return "newcomer"
        return "same" if prior == t else "transfer"

    ps["cat"] = [category(p, y, t) for p, y, t in zip(ps["player_id"], ps["season"], ps["team_id"])]
    ps["n_prior"] = [sum(1 for s in seasons_by_player[p] if s < y) for p, y in zip(ps["player_id"], ps["season"])]

    # Y-1 minutes on T (all Y-1 games) and whether each of those players appears for T in Y pre-cutoff.
    full_pt = pg.groupby(["season", "team_id", "player_id"], as_index=False)["minutes"].sum()
    appear = set(zip(ps["season"], ps["team_id"], ps["player_id"]))
    full_pt["returns_next"] = [(y + 1, t, p) in appear for y, t, p in zip(full_pt["season"], full_pt["team_id"], full_pt["player_id"])]
    prior_tot = full_pt.groupby(["season", "team_id"])["minutes"].sum()
    prior_ret = full_pt[full_pt["returns_next"]].groupby(["season", "team_id"])["minutes"].sum()

    # Team universe: every D1 team with a pre-cutoff D1-vs-D1 game in a season with player data.
    teams = tg[tg["pre_cutoff"]][["season", "team_id"]].drop_duplicates()
    teams = teams[teams["season"].isin(data_seasons) & (teams["season"] <= LAST_SEASON)]
    teams = teams.sort_values(["season", "team_id"]).reset_index(drop=True)

    ps["w_prior"] = ps["minutes"] * ps["n_prior"]
    g = ps.groupby(["season", "team_id"])
    agg = pd.DataFrame({
        "team_min_obs": g["minutes"].sum(),
        "team_pts_obs": g["points"].sum(),
        "w_prior": g["w_prior"].sum(),
    })
    for cat in ("same", "transfer", "newcomer"):
        agg[f"{cat}_min"] = ps[ps["cat"] == cat].groupby(["season", "team_id"])["minutes"].sum()
    agg["same_pts"] = ps[ps["cat"] == "same"].groupby(["season", "team_id"])["points"].sum()
    agg = agg.reset_index()

    out = teams.merge(agg, on=["season", "team_id"], how="left")
    out = out.merge(closure(pg, tg, stats), on=["season", "team_id"], how="left")
    out["team_min_obs"] = out["team_min_obs"].fillna(0.0)

    has_min = out["team_min_obs"] > 0
    for cat, col in (("same", "ret_same_min_pct"), ("transfer", "transfer_min_pct"), ("newcomer", "newcomer_min_pct")):
        out[col] = np.where(has_min, out[f"{cat}_min"].fillna(0.0) / out["team_min_obs"].where(has_min), np.nan)
    has_pts = out["team_pts_obs"].fillna(0) > 0
    out["ret_same_pts_pct"] = np.where(has_pts, out["same_pts"].fillna(0.0) / out["team_pts_obs"].where(has_pts), np.nan)
    out["exp_prior_seasons"] = np.where(has_min, out["w_prior"] / out["team_min_obs"].where(has_min), np.nan)

    denom = [prior_tot.get((y - 1, t), 0.0) for y, t in zip(out["season"], out["team_id"])]
    numer = [prior_ret.get((y - 1, t), 0.0) for y, t in zip(out["season"], out["team_id"])]
    out["ret_prior_min_pct"] = [n / d if d > 0 else np.nan for n, d in zip(numer, denom)]

    # No player data in Y-1: continuity and experience are unknown.
    no_prev = ~out["season"].sub(1).isin(data_seasons)
    for col in ("ret_same_min_pct", "transfer_min_pct", "newcomer_min_pct", "ret_prior_min_pct",
                "ret_same_pts_pct", "exp_prior_seasons"):
        out.loc[no_prev, col] = np.nan
    out["exp_censored"] = (out["season"] - first_season) < 4

    out["roster_quality"] = np.select(
        [out["min_closure_pct"] >= QUALITY_OK, out["min_closure_pct"] >= QUALITY_PARTIAL],
        ["ok", "partial"], default="poor")

    cols = ["season", "team_id", "team_min_obs", "min_closure_pct", "roster_quality",
            "ret_same_min_pct", "transfer_min_pct", "newcomer_min_pct", "ret_prior_min_pct",
            "ret_same_pts_pct", "exp_prior_seasons", "exp_censored"]
    out = out[cols].sort_values(["season", "team_id"]).reset_index(drop=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False, float_format="%.6f")
    stats["rows_out"] = len(out)
    return out, stats


if __name__ == "__main__":
    out, stats = build()
    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"wrote {OUT_PATH} ({len(out)} rows)")
