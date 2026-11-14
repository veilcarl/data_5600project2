"""Crystal Ball dataset v2: one row per D1 team-season, 2005-2026 except 2020, pre-Selection-Sunday features.

Inputs (from the repo root, after the extracts and feature scripts have run):
  data/interim/base.csv         scripts/export_base_v2.sql (ratings, metrics, seeds, conference, AP week 6)
  data/interim/outcome.csv      scripts/features/outcome.py (NCAA tournament results; tournament teams only)
  data/interim/team_games.csv   scripts/features/team_games.py (D1-vs-D1 game features)
  data/interim/roster.csv       scripts/features/roster.py (roster continuity; 2015+)
  data/raw/team_games_rows.csv  scripts/features/team_games_extract.sql (only to flag games with no period count)
Output:
  data/processed/champion_checklist_v2.csv
  data/processed/coverage_v2.md   per season: non-null % of every column for seeded teams; roster_quality,
                                  location_quality and data_issue counts (all teams)

Joins: left joins on (season, team_id) starting from base. Renamed: team_games games/wins/losses -> d1_games/d1_wins/
d1_losses (base wins/losses count every opponent). base.champion (from tournament_finish) is checked against
outcome.champion and dropped. tournament_region and tournament_finish are read for the checks but not written.
Missing sources stay NULL, never 0: outcome columns are NULL for teams not in the NCAA tournament, roster columns for
seasons before 2015 (continuity columns also for 2015, which has no prior season of player data).
Added:
  wab_z                     WAB standardized within season: (wab - season mean) / season std (population, ddof=0)
  roster_lookback_censored  True for 2016 (the Y-2 lookback for sit-out/redshirt years hits 2014, which has no
                            player data), False for 2017+, NULL where continuity is NULL
  data_issue                ';'-separated known, unfixed data problems for that team-season (NULL = none known)
The build stops (SystemExit) unless every check in check() holds.

Run:  .venv/bin/python scripts/build_dataset.py
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INTERIM = ROOT / "data/interim"
TG_ROWS = ROOT / "data/raw/team_games_rows.csv"
OUT_PATH = ROOT / "data/processed/champion_checklist_v2.csv"
COVERAGE_PATH = ROOT / "data/processed/coverage_v2.md"
# Read for the checks, not written: tournament_region is filled only for 2026; tournament_finish is an outcome
# (Champion / Runner-Up / Final Four only) that outcome.csv's columns cover.
NOT_OUTPUT = ["tournament_region", "tournament_finish"]
KEY = ["season", "team_id"]

# Known, unfixed upstream problems: (season, team_id, issue). Team ids are macfax core_team ids.
KNOWN_ISSUES = [
    (2017, 82, "player_omitted_espn"),            # Eastern Washington: ESPN omits one player from every box (674 pts)
    (2011, 341, "game_missing_vs_liu_2011"),      # Vermont-LIU (ESPN 313240261): ESPN has only the first half, not stored
    (2011, 138, "game_missing_vs_vermont_2011"),  # LIU, same game
    (2026, 252, "score_conflict_ncaa_espn"),      # game 5781 SIU Edwardsville 71 - Eastern Illinois 76 (NCAA score kept)
    (2026, 79, "score_conflict_ncaa_espn"),
    (2026, 23, "score_conflict_ncaa_espn"),       # game 5852 Belmont 81 - Drake 100
    (2026, 72, "score_conflict_ncaa_espn"),
    (2026, 189, "score_conflict_ncaa_espn"),      # game 5858 Murray St. 80 - Illinois Chicago 94
    (2026, 121, "score_conflict_ncaa_espn"),
    (2026, 28, "box_points_short_game77"),        # game 77 BU 76 at Northeastern 75 (OT): BU box rows sum to 74
    (2026, 212, "box_points_short_game77"),
]
ROSTER_SHARES = ["ret_same_min_pct", "transfer_min_pct", "newcomer_min_pct"]
ROSTER_CONTINUITY = ROSTER_SHARES + ["ret_prior_min_pct", "ret_same_pts_pct", "exp_prior_seasons"]


def _bool(s: pd.Series) -> pd.Series:
    return s.map({"t": True, "f": False, True: True, False: False, "True": True, "False": False})


def load():
    base = pd.read_csv(INTERIM / "base.csv")
    for c in ("is_reclassifying", "made_tournament"):
        base[c] = _bool(base[c]).astype(bool)
    outcome = pd.read_csv(INTERIM / "outcome.csv")
    tg = pd.read_csv(INTERIM / "team_games.csv").rename(columns={"games": "d1_games", "wins": "d1_wins", "losses": "d1_losses"})
    roster = pd.read_csv(INTERIM / "roster.csv")
    tg_rows = pd.read_csv(TG_ROWS, usecols=["season", "team_id", "periods"], dtype={"periods": "Int64"})
    return base, outcome, tg, roster, tg_rows


def fail(msg: str):
    raise SystemExit(f"CHECK FAILED: {msg}")


def build():
    base, outcome, tg, roster, tg_rows = load()
    base = base[base["season"] != 2020]
    for name, df in (("base", base), ("outcome", outcome), ("team_games", tg), ("roster", roster)):
        dups = df.duplicated(KEY).sum()
        if dups:
            fail(f"{name} has {dups} duplicate (season, team_id) rows")

    d = base.merge(outcome.rename(columns={"champion": "champion_outcome"}).assign(_in_outcome=True), on=KEY, how="left")
    d = d.merge(tg.assign(_in_tg=True), on=KEY, how="left")
    d = d.merge(roster.assign(_in_roster=True), on=KEY, how="left")
    for c in ("_in_outcome", "_in_tg", "_in_roster"):
        d[c] = d[c].fillna(False).astype(bool)
    d = d[d["season"] != 2020].copy()

    # base.champion (tournament_finish == 'Champ') must agree with the game-based champion, then is dropped.
    if not (d["champion"].eq(1) == d["champion_outcome"].eq(True)).all():
        fail("base champion (tournament_finish) disagrees with outcome champion")
    d = d.drop(columns=["champion"]).rename(columns={"champion_outcome": "champion"})

    # Derived columns
    g = d.groupby("season")["wab"]
    d["wab_z"] = (d["wab"] - g.transform("mean")) / g.transform(lambda s: s.std(ddof=0))
    has_cont = d["ret_same_min_pct"].notna()
    d["roster_lookback_censored"] = pd.array(np.where(has_cont, d["season"] == 2016, None), dtype="boolean")

    issues = {}
    for season, team, issue in KNOWN_ISSUES:
        issues.setdefault((season, team), []).append(issue)
    unk = tg_rows[tg_rows["periods"].isna()].groupby(KEY).size()
    for (season, team), n in unk.items():
        issues.setdefault((season, team), []).append(f"ot_period_unknown_{n}g")
    for (season, team, q) in d.loc[d["roster_quality"].isin(["partial", "poor"]), ["season", "team_id", "roster_quality"]].itertuples(index=False):
        issues.setdefault((season, team), []).append(f"player_rows_incomplete_{q}")
    missing_keys = set(k for k, _ in issues.items()) - set(zip(d["season"], d["team_id"]))
    missing_keys = {k for k in missing_keys if k[0] != 2020}
    if missing_keys:
        fail(f"data_issue entries for team-seasons not in the dataset: {sorted(missing_keys)}")
    d["data_issue"] = [";".join(issues.get((s, t), [])) or None for s, t in zip(d["season"], d["team_id"])]

    check(d)
    d = d.drop(columns=["_in_outcome", "_in_tg", "_in_roster"])
    out_cols = [c for c in base.columns if c != "champion" and c not in NOT_OUTPUT] + ["wab_z"] + \
               [c for c in outcome.columns if c not in KEY] + [c for c in tg.columns if c not in KEY] + \
               [c for c in roster.columns if c not in KEY] + ["roster_lookback_censored", "data_issue"]
    d = d[out_cols].sort_values(KEY).reset_index(drop=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(OUT_PATH, index=False, float_format="%.6f")
    write_coverage(d)
    return d


def write_coverage(d: pd.DataFrame):
    seasons = sorted(d["season"].unique())
    seeded = d[d["tournament_seed"].notna()]
    lines = ["# Coverage: champion_checklist_v2.csv", "",
             f"Generated by `scripts/build_dataset.py`. {len(d)} rows, {d.shape[1]} columns, seasons "
             f"{seasons[0]}-{seasons[-1]} except 2020.", "",
             "## Non-null % per column, seeded teams only", "",
             "Columns 100% non-null for seeded teams in every season are listed once, not tabled. NULL is expected in",
             "some columns: `ap_poll_week6` (unranked), roster columns before 2015/2016, location and Q1 columns",
             "2005-2007, `data_issue` (empty = no known issue).", ""]
    pct = seeded.groupby("season").agg(lambda s: s.notna().mean() * 100).T
    full = [c for c in pct.index if (pct.loc[c] == 100).all()]
    lines += ["100% in every season: " + ", ".join(f"`{c}`" for c in full), ""]
    part = pct.drop(index=full)
    lines.append("| column | " + " | ".join(str(y) for y in seasons) + " |")
    lines.append("|---|" + "---:|" * len(seasons))
    for c, row in part.iterrows():
        lines.append(f"| `{c}` | " + " | ".join(f"{row[y]:.0f}" for y in seasons) + " |")
    lines += ["", f"Seeded teams per season: " + ", ".join(f"{y}: {n}" for y, n in seeded.groupby("season").size().items()), ""]

    def count_table(title, col, values):
        out = ["", f"## {title} (all teams)", "", "| season | " + " | ".join(values) + " |", "|---|" + "---:|" * len(values)]
        for y in seasons:
            x = d.loc[d["season"] == y, col]
            out.append(f"| {y} | " + " | ".join(str(int((x == v).sum()) if v != "(null)" else int(x.isna().sum())) for v in values) + " |")
        return out
    lines += count_table("roster_quality", "roster_quality", ["ok", "partial", "poor", "(null)"])
    lines += count_table("location_quality", "location_quality", ["ok", "partial", "none"])
    issues = d[["season", "data_issue"]].dropna().copy()
    issues["data_issue"] = issues["data_issue"].str.split(";")
    issues = issues.explode("data_issue")
    issues["data_issue"] = issues["data_issue"].str.replace(r"_\d+g$", "", regex=True)
    kinds = sorted(issues["data_issue"].unique())
    tab = issues.groupby(["season", "data_issue"]).size().unstack(fill_value=0).reindex(index=seasons, columns=kinds, fill_value=0)
    lines += ["", "## data_issue counts (team-seasons with each issue; all teams)", "",
              "| season | " + " | ".join(f"`{k}`" for k in kinds) + " | rows with any |", "|---|" + "---:|" * (len(kinds) + 1)]
    any_issue = d.groupby("season")["data_issue"].apply(lambda s: int(s.notna().sum()))
    for y in seasons:
        lines.append(f"| {y} | " + " | ".join(str(int(tab.loc[y, k])) for k in kinds) + f" | {any_issue[y]} |")
    COVERAGE_PATH.write_text("\n".join(lines) + "\n")


def check(d: pd.DataFrame):
    if d.duplicated(KEY).any():
        fail("duplicate (season, team_id) rows")
    if (d["season"] == 2020).any():
        fail("2020 rows present")
    if not d["_in_tg"].all():
        fail(f"{(~d['_in_tg']).sum()} rows have no team_games row")

    # Outcome: tournament teams are exactly the seeded teams and the outcome rows; closure per season.
    if not (d["made_tournament"] == d["_in_outcome"]).all():
        fail("made_tournament (seed) disagrees with presence in outcome.csv")
    t = d[d["_in_outcome"]]
    for season, x in t.groupby("season"):
        want = 65 if season <= 2010 else 68
        reach = [int((x["rounds_won"] >= k).sum()) for k in range(1, 7)]
        ff = int(x["first_four"].sum())
        if (len(x), int(x["rounds_won"].sum()), reach, ff) != (want, 63, [32, 16, 8, 4, 2, 1], 2 if season <= 2010 else 8):
            fail(f"outcome closure {season}: teams {len(x)}, rounds {x['rounds_won'].sum()}, reach {reach}, first four {ff}")
        if int(x["champion"].sum()) != 1:
            fail(f"{season}: {int(x['champion'].sum())} champions")
        if set(x.loc[x["tournament_finish"] == "Champ", "team_id"]) != set(x.loc[x["champion"] == True, "team_id"]):  # noqa: E712
            fail(f"{season}: champion differs from tournament_finish")
    if d.loc[~d["_in_outcome"], "champion"].notna().any():
        fail("non-tournament rows carry outcome values")
    if (d.groupby("season")["champion"].apply(lambda s: (s == True).sum()) != 1).any():  # noqa: E712
        fail("not exactly one champion per season")

    # Roster shares sum to 1 where not null.
    sh = d[ROSTER_SHARES]
    full = sh.notna().all(axis=1)
    if (sh.notna().any(axis=1) & ~full).any():
        fail("roster shares partly NULL in a row")
    if ((sh[full].sum(axis=1) - 1).abs() > 1e-3).any():
        fail("roster shares do not sum to 1")

    # No feature is 0 where its source is missing.
    src_cols = {"_in_outcome": ["first_four", "rounds_won", "made_r32", "made_s16", "made_e8", "made_f4", "champion"],
                "_in_roster": ["team_min_obs", "min_closure_pct", "roster_quality"] + ROSTER_CONTINUITY + ["exp_censored"]}
    for flag, cols in src_cols.items():
        bad = d.loc[~d[flag], cols].notna().sum()
        if bad.any():
            fail(f"columns filled without their source ({flag}): {bad[bad > 0].to_dict()}")
    if d.loc[d["season"] <= 2015, ROSTER_CONTINUITY].notna().any().any():
        fail("roster continuity filled where no prior player season exists")
    if (d.loc[d["_in_roster"], "team_min_obs"] == 0).any():
        fail("team_min_obs is 0 (no player rows) instead of NULL")
    loc_cols = ["road_games", "road_wins", "road_win_pct", "neutral_games", "neutral_wins", "q1_games", "q1_wins"]
    if d.loc[d["location_quality"] == "none", loc_cols].notna().any().any():
        fail("location features filled in seasons with no location data")
    if d["wab"].isna().any() or d["wab_z"].isna().any():
        fail("wab / wab_z missing")
    for col, src in (("three_par", "fga"), ("opp_three_par", "opp_fga")):
        if (d[src].isna() & d[col].notna()).any():
            fail(f"{col} filled where {src} is missing")


if __name__ == "__main__":
    out = build()
    print(f"wrote {OUT_PATH} ({len(out)} rows, {out.shape[1]} columns) and {COVERAGE_PATH}")
