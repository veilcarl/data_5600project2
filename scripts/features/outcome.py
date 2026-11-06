"""NCAA tournament outcome labels: one row per team in each NCAA tournament, 2005-2026 (no 2020).

Inputs (run scripts/features/outcome_extract.sql first, from the repo root):
  data/raw/outcome_games.csv   postseason candidate games (ESPN season.type 3; 2026 championshipId 6393)
  data/raw/outcome_seeds.csv   tournament_seed / tournament_finish (post-tournament rating rows)
  data/raw/outcome_teams.csv   team names (for the override list and reports)
Output:
  data/interim/outcome.csv

NCAA game rule
  2005-2025: season.type 3 and an NCAA headline ("MEN'S BASKETBALL CHAMP...", "NCAA", "FINAL FOUR",
             "NATIONAL CHAMPIONSHIP", "CHAMPIONSHIP AT <city>", "<CITY> REGIONAL" / "<X> REGION");
             NIT / CBI / CIT / CollegeInsider / Vegas 16 / TBC / Crown headlines excluded.
  2026:      championshipId = 6393.
First Four / Opening Round (game_date is a UTC date, so it is not used):
  headline "OPENING ROUND" / "PLAY-IN" / "FIRST FOUR"; 2011-2015 headline "1ST ROUND" (the NCAA called the
  First Four the first round then); 2026 bracketRound = 1; otherwise a game whose US-Eastern start date is
  on or before Selection Sunday + 3 days (Tue/Wed). The 2021 First Four was on a Thursday but is headlined.
rounds_won: wins in NCAA games after the First Four (0-6). A 0-0 game (no-contest) has no winner.

Run:  .venv/bin/python scripts/features/outcome.py
"""

from datetime import timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw"
OUT_PATH = ROOT / "data/interim/outcome.csv"

OTHER_EVENTS = r"(?:^|\W)(?:NIT|CBI|CIT|VEGAS 16|COLLEGEINSIDE|BASKETBALL CLASSIC|TBC|CROWN|COLLEGE BASKETBALL INVITATIONAL)(?:\W|$)"
NCAA_HEADLINE = r"(?:MEN'S BASKETBALL CHAMP|NCAA|FINAL FOUR|NATIONAL CHAMPIONSHIP|^CHAMPIONSHIP AT |REGIONAL|REGION\b)"
FIRST_FOUR_HEADLINE = r"(?:OPENING ROUND|PLAY-IN|FIRST FOUR)"

# Known gaps in the Game table, patched by hand. (season, team name, field, value, reason)
#   rounds_won entries are added to the computed count; first_four entries set the flag.
#   No Oregon entry: the 2021 VCU no-contest is stored as an Oregon 1-0 "win" (headline "Oregon advances due
#   to uncontested game"), so Oregon's advance is already counted and VCU stays at 0.
OVERRIDES = [
    (2021, "Baylor", "rounds_won", +1, "beat Hartford in the Round of 64; game missing (Hartford has no Team row)"),
    (2017, "Mount St. Mary's", "first_four", True, "First Four win over New Orleans; game missing"),
    (2017, "New Orleans", "first_four", True, "First Four loss to Mount St. Mary's; game missing"),
    (2017, "Kansas St.", "first_four", True, "First Four win over Wake Forest; game missing"),
    (2017, "Wake Forest", "first_four", True, "First Four loss to Kansas St.; game missing"),
    (2018, "Radford", "first_four", True, "First Four win over LIU; game missing"),
    (2018, "LIU", "first_four", True, "First Four loss to Radford; game missing"),
]

# Boston College's 2005-2009 NCAA games are stored under team 28 (Boston University); fixed upstream
# (Tasks 6c/6d) before the final build. Not worked around here, only reported.
BC_BU_MERGED_TEAM = 28


def load():
    games = pd.read_csv(RAW / "outcome_games.csv", dtype={"championship_id": "string", "bracket_round": "string"})
    seeds = pd.read_csv(RAW / "outcome_seeds.csv")
    teams = pd.read_csv(RAW / "outcome_teams.csv")
    games["start_utc"] = pd.to_datetime(games["start_utc"], utc=True)
    games["selection_sunday_date"] = pd.to_datetime(games["selection_sunday_date"]).dt.date
    games["headline_u"] = games["headline"].fillna("").str.upper()
    return games, seeds, teams


def classify(games: pd.DataFrame) -> pd.DataFrame:
    g = games.copy()
    espn = g["season"] <= 2025
    is_other = g["headline_u"].str.contains(OTHER_EVENTS, regex=True)
    g["is_ncaa"] = (espn & ~is_other & g["headline_u"].str.contains(NCAA_HEADLINE, regex=True)) | (
        ~espn & (g["championship_id"] == "6393"))
    local_date = g["start_utc"].dt.tz_convert("America/New_York").dt.date
    g["ff_by_time"] = [d <= ss + timedelta(days=3) for d, ss in zip(local_date, g["selection_sunday_date"])]
    ff_head = g["headline_u"].str.contains(FIRST_FOUR_HEADLINE, regex=True)
    ff_head |= g["season"].between(2011, 2015) & g["headline_u"].str.contains(r"- 1ST ROUND", regex=True)
    ff_head |= ~espn & (g["bracket_round"] == "1")
    g["ff_by_headline"] = ff_head
    g["first_four"] = g["ff_by_headline"] | g["ff_by_time"]
    g = g[g["is_ncaa"]].copy()
    played = ~((g["home_score"] == 0) & (g["away_score"] == 0))
    g["winner"] = pd.NA
    g.loc[played & (g["home_score"] > g["away_score"]), "winner"] = g["home_team_id"]
    g.loc[played & (g["away_score"] > g["home_score"]), "winner"] = g["away_team_id"]
    return g


def build():
    games, seeds, teams = load()
    g = classify(games)
    name_to_id = dict(zip(teams["team_name"], teams["team_id"]))

    part = pd.concat([
        g[["season", "home_team_id", "first_four"]].rename(columns={"home_team_id": "team_id"}),
        g[["season", "away_team_id", "first_four"]].rename(columns={"away_team_id": "team_id"}),
    ])
    seeded = seeds[seeds["tournament_seed"].notna()][["season", "team_id"]]
    universe = pd.concat([part[["season", "team_id"]], seeded]).drop_duplicates()

    ff_teams = set(map(tuple, part[part["first_four"]][["season", "team_id"]].values))
    wins = (g[~g["first_four"] & g["winner"].notna()]
            .assign(team_id=lambda d: d["winner"].astype(int))
            .groupby(["season", "team_id"]).size().rename("rounds_won"))

    out = universe.copy()
    out["first_four"] = [(s, t) in ff_teams for s, t in zip(out["season"], out["team_id"])]
    out = out.merge(wins.reset_index(), on=["season", "team_id"], how="left")
    out["rounds_won"] = out["rounds_won"].fillna(0).astype(int)

    applied = []
    for season, name, field, value, reason in OVERRIDES:
        tid = name_to_id[name]
        mask = (out["season"] == season) & (out["team_id"] == tid)
        if not mask.any():
            raise SystemExit(f"override target not in tournament universe: {season} {name}")
        if field == "rounds_won":
            out.loc[mask, "rounds_won"] += value
        else:
            out.loc[mask, field] = value
        applied.append((season, name, field, value, reason))

    for k, col in enumerate(["made_r32", "made_s16", "made_e8", "made_f4"], start=1):
        out[col] = out["rounds_won"] >= k
    out["champion"] = out["rounds_won"] == 6
    out = out.sort_values(["season", "team_id"]).reset_index(drop=True)
    cols = ["season", "team_id", "first_four", "rounds_won", "made_r32", "made_s16", "made_e8", "made_f4", "champion"]
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out[cols].to_csv(OUT_PATH, index=False)
    return out[cols], g, seeds, teams, applied


if __name__ == "__main__":
    out, g, seeds, teams, applied = build()
    print(f"wrote {OUT_PATH} ({len(out)} rows); NCAA games classified: {len(g)}; overrides applied: {len(applied)}")
