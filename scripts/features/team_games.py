"""Team-game features: one row per D1 team-season, 2005-2026 except 2020 (pre-cutoff, D1 vs D1, 0-0 excluded).

Input (run scripts/features/team_games_extract.sql first, from the repo root):
  data/raw/team_games_rows.csv   one row per team per pre-cutoff game
Output:
  data/interim/team_games.csv

Columns
  games, wins, losses             D1-vs-D1 record from home_score / away_score
  fga, fg3a, three_par            team box rows with fga > 0
  opp_fga, opp_fg3a, opp_three_par   opponent's box row in the same game (fga > 0)
  opp_box_coverage                share of games with a usable opponent row
  road_games/wins/win_pct, neutral_games/wins
      true road = T is away and the game is not neutral.
      2008-2025: T's box home_away (H/A/N); if T's box row is missing, Game.neutral_site + Game home/away
      (they agree with the box in those seasons). 2026: Game.neutral_site + Game home/away (2026 box rows
      never say 'N'). 2005-2007: NULL (no neutral-site flags).
  location_quality                'none' 2005-07, 'partial' 2026, else 'ok'
  last10_wins, last10_avg_margin  T's last 10 games on or before the cutoff, by game start time
  close5_games, close5_wins       final margin <= 5
  ot_games, ot_wins               periods > 2 (raw status.period 2005-2025 with the 2018 regulation fix;
                                  period_count 2026); games with an unknown period count are not counted
  q1_games, q1_wins               Quad 1 proxy: opponent pre-tournament rank_adj_em <= 30 home, <= 50 neutral,
                                  <= 75 away; NULL where location_quality = 'none'

Run:  .venv/bin/python scripts/features/team_games.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
IN_PATH = ROOT / "data/raw/team_games_rows.csv"
OUT_PATH = ROOT / "data/interim/team_games.csv"

NO_LOCATION_SEASONS = range(2005, 2008)
PARTIAL_LOCATION_SEASONS = {2026}
Q1_RANK = {"home": 30, "neutral": 50, "away": 75}


def _flag(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["t", "true"])


def location(d: pd.DataFrame, stats: dict) -> pd.Series:
    """'home' / 'away' / 'neutral', or NA where location is unknown (2005-2007)."""
    from_game = np.where(d["game_neutral"], "neutral", np.where(d["is_game_home"], "home", "away"))
    from_box = d["box_home_away"].map({"H": "home", "A": "away", "N": "neutral"})
    loc = pd.Series(np.where(d["season"].isin(PARTIAL_LOCATION_SEASONS), from_game, from_box), index=d.index)
    box_missing = ~d["season"].isin(PARTIAL_LOCATION_SEASONS) & d["box_home_away"].isna()
    stats["location_from_game_fallback_rows"] = int((box_missing & ~d["season"].isin(NO_LOCATION_SEASONS)).sum())
    loc[box_missing] = pd.Series(from_game, index=d.index)[box_missing]
    loc[d["season"].isin(NO_LOCATION_SEASONS)] = pd.NA
    return loc


def build():
    stats = {}
    d = pd.read_csv(IN_PATH, dtype={"box_home_away": "string", "periods": "Int64", "opp_rank_adj_em": "Int64"})
    d["is_game_home"] = _flag(d["is_game_home"])
    d["game_neutral"] = _flag(d["game_neutral"])
    d["start_utc"] = pd.to_datetime(d["start_utc"], utc=True)
    d["win"] = d["pts"] > d["opp_pts"]
    d["margin"] = d["pts"] - d["opp_pts"]
    d["loc"] = location(d, stats)
    stats["rows_in"] = len(d)
    stats["ot_unknown_period_rows"] = int(d["periods"].isna().sum())
    stats["ot_unknown_period_by_season"] = d[d["periods"].isna()].groupby("season").size().to_dict()
    stats["q1_opp_rank_missing_rows"] = int(d["opp_rank_adj_em"].isna().sum())

    team_ok = d["fga"].fillna(0) > 0
    opp_ok = d["opp_fga"].fillna(0) > 0
    d["fga_u"] = d["fga"].where(team_ok)
    d["fg3a_u"] = d["fg3a"].where(team_ok)
    d["opp_fga_u"] = d["opp_fga"].where(opp_ok)
    d["opp_fg3a_u"] = d["opp_fg3a"].where(opp_ok)
    d["opp_ok"] = opp_ok
    d["road"] = d["loc"] == "away"
    d["neutral"] = d["loc"] == "neutral"
    d["close5"] = d["margin"].abs() <= 5
    d["ot"] = d["periods"].fillna(0) > 2
    thr = d["loc"].map(Q1_RANK)
    d["q1"] = d["opp_rank_adj_em"].notna() & thr.notna() & (d["opp_rank_adj_em"].astype("float") <= thr.astype("float"))

    key = ["season", "team_id"]
    g = d.groupby(key)
    out = pd.DataFrame({
        "games": g.size(),
        "wins": g["win"].sum(),
        "fga": g["fga_u"].sum(min_count=1),
        "fg3a": g["fg3a_u"].sum(min_count=1),
        "opp_fga": g["opp_fga_u"].sum(min_count=1),
        "opp_fg3a": g["opp_fg3a_u"].sum(min_count=1),
        "opp_box_coverage": g["opp_ok"].mean(),
        "road_games": g["road"].sum(),
        "road_wins": (d["road"] & d["win"]).groupby([d["season"], d["team_id"]]).sum(),
        "neutral_games": g["neutral"].sum(),
        "neutral_wins": (d["neutral"] & d["win"]).groupby([d["season"], d["team_id"]]).sum(),
        "close5_games": g["close5"].sum(),
        "close5_wins": (d["close5"] & d["win"]).groupby([d["season"], d["team_id"]]).sum(),
        "ot_games": g["ot"].sum(),
        "ot_wins": (d["ot"] & d["win"]).groupby([d["season"], d["team_id"]]).sum(),
        "q1_games": g["q1"].sum(),
        "q1_wins": (d["q1"] & d["win"]).groupby([d["season"], d["team_id"]]).sum(),
    }).reset_index()
    out["losses"] = out["games"] - out["wins"]
    out["three_par"] = out["fg3a"] / out["fga"]
    out["opp_three_par"] = out["opp_fg3a"] / out["opp_fga"]
    out["road_win_pct"] = np.where(out["road_games"] > 0, out["road_wins"] / out["road_games"].where(out["road_games"] > 0), np.nan)

    # Last 10 games on or before the cutoff, newest first by start time (cumcount, not groupby().tail(),
    # which segfaults in pandas 3.1 / Python 3.14).
    last10 = (d.sort_values(["start_utc", "game_id"], ascending=False)
               .assign(rk=lambda x: x.groupby(key).cumcount())
               .query("rk < 10"))
    l10 = last10.groupby(key).agg(last10_wins=("win", "sum"), last10_avg_margin=("margin", "mean")).reset_index()
    out = out.merge(l10, on=key, how="left")

    no_loc = out["season"].isin(NO_LOCATION_SEASONS)
    for c in ("road_games", "road_wins", "road_win_pct", "neutral_games", "neutral_wins", "q1_games", "q1_wins"):
        out[c] = out[c].astype("float").where(~no_loc)
    out["location_quality"] = np.select([no_loc, out["season"].isin(PARTIAL_LOCATION_SEASONS)], ["none", "partial"], default="ok")

    int_cols = ["games", "wins", "losses", "fga", "fg3a", "opp_fga", "opp_fg3a", "road_games", "road_wins",
                "neutral_games", "neutral_wins", "last10_wins", "close5_games", "close5_wins", "ot_games", "ot_wins",
                "q1_games", "q1_wins"]
    for c in int_cols:
        out[c] = out[c].astype("Int64")
    cols = ["season", "team_id", "games", "wins", "losses", "fga", "fg3a", "three_par", "opp_fga", "opp_fg3a",
            "opp_three_par", "opp_box_coverage", "road_games", "road_wins", "road_win_pct", "neutral_games",
            "neutral_wins", "location_quality", "last10_wins", "last10_avg_margin", "close5_games", "close5_wins",
            "ot_games", "ot_wins", "q1_games", "q1_wins"]
    out = out[cols].sort_values(key).reset_index(drop=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_PATH, index=False, float_format="%.6f")
    stats["rows_out"] = len(out)
    return out, stats


if __name__ == "__main__":
    out, stats = build()
    for k, v in stats.items():
        print(f"{k}: {v}")
    print(f"wrote {OUT_PATH} ({len(out)} rows)")
