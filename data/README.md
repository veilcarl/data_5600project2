# NCAA Champion Checklist — DATA 5600

Three versions of the dataset live in `processed/`:

| File | Built by | Status |
|---|---|---|
| `processed/champion_checklist_v3.csv` | `scripts/build_dataset.py` | **Current.** Use this one. |
| `processed/champion_checklist_v2.csv` | `scripts/build_dataset.py` (v2 version) | v2, kept unchanged for reference |
| `processed/champion_checklist.csv` | `scripts/export_champion_checklist.sql` | v1, kept unchanged for reference |

`processed/coverage_v3.md` lists, per season, the non-null share of every v3 column for seeded teams and the
`roster_quality`, `location_quality` and `data_issue` counts (`coverage_v2.md` is the same for v2).

---

## v3: `processed/champion_checklist_v3.csv`

One row per NCAA Division I team-season, 2005–2026 except 2020 (no tournament). 7,343 rows, 87 columns.

**v3 vs v2:** same rows and the same non-roster columns and values. The roster columns now start in 2005
(player box scores for 2005–2014 were added to MacFax), two columns are new (`ncaa_filled_min_pct`,
`player_data_games_pct`), players ESPN left out of its 2022–23 and 2023–24 box scores are filled from ncaa.com,
and `data_issue` gains `player_rows_incomplete_*` entries for 2005–2014.

- **D1** means a member of Division I *that season* (MacFax `TeamSeasonMembership`), not "D1 today". A team-season
  is included when it was D1 and played at least one D1-vs-D1 game on or before Selection Sunday.
- **Pre-tournament only.** Every feature uses games on or before that season's Selection Sunday (canceled 0-0
  games excluded). The outcome columns are the only post-Selection-Sunday information; they are labels, not
  predictors.
- **Key:** (`season`, `team_id`). `season` is the ending year (2026 = the 2025–26 season).
- **NULL means unknown or not applicable, never 0.** Each column's coverage is listed below.
- **Built from the local MacFax database.** Non-roster columns: macfax main as of 2026-11-13 (data fixes through
  Task 8c.2), unchanged from v2. Roster columns: as of 2026-11-19, after the 2005–2014 player backfill. Numbers
  change if the database is rebuilt or recomputed.

### Identity and membership

| Column | Definition | Seasons | Caveats |
|---|---|---|---|
| `season` | Ending year of the season | all | |
| `team`, `team_slug`, `team_id` | MacFax team name, slug and id | all | Names are MacFax's (e.g. "Connecticut", "NC State") |
| `is_reclassifying` | In an NCAA transition from Division II/III that season (counts as D1, not yet tournament-eligible) | all | Set from each school's first D1 season in MacFax, so transitions that began **before 2006** are missed (MacFax data starts in 2005). Checked against Wikipedia's "ineligible due to transition" standings marks where they exist (most seasons from 2013); earlier flags follow the known transition windows. |
| `conference` | Conference code that season (e.g. `B10`, `WCC`; `IND` = Independent, `GWC` = Great West) | all | From the season's conference-membership history (Wikipedia, cross-checked with ESPN conference-game flags). Renamed leagues share one code: Mid-Continent → `Sum`, Pac-10 → `P12`, original Big East → `BE`. |

### Tournament field and outcome labels

| Column | Definition | Seasons | Caveats |
|---|---|---|---|
| `made_tournament` | Received an NCAA tournament seed | all | |
| `tournament_seed` | Seed 1–16 | all | NULL for non-tournament teams |
| `first_four` | Played in the First Four / opening round | all | NULL for non-tournament teams |
| `rounds_won` | NCAA wins after the First Four, 0–6 | all | From game results. NULL for non-tournament teams. The 2021 VCU–Oregon no-contest counts as an Oregon win. |
| `made_r32`, `made_s16`, `made_e8`, `made_f4` | `rounds_won` ≥ 1, 2, 3, 4 | all | NULL for non-tournament teams |
| `champion` | `rounds_won` = 6 | all | NULL for non-tournament teams; exactly one per season |

### Season record and efficiency (pre-tournament ratings)

| Column | Definition | Seasons | Caveats |
|---|---|---|---|
| `games_played`, `wins`, `losses`, `win_pct` | Record from game scores | all | **Counts all opponents, including non-D1.** For D1-only records use the `d1_` columns. |
| `adj_o`, `adj_d`, `adj_em` | Opponent-adjusted points per 100 possessions scored, allowed, and their difference | all | MacFax's own ratings (KenPom-style), D1-vs-D1 games |
| `adj_tempo` | Adjusted possessions per 40 minutes | all | **Pace per 40 minutes** (overtime minutes are scaled out) |
| `rank_adj_o`, `rank_adj_d`, `rank_adj_em` | Rank among that season's D1 teams | all | |
| `adj_efg_pct`, `adj_opp_efg_pct`, `adj_efg_margin` | Opponent-adjusted effective FG% for, against, and margin | all | |
| `adj_tov_pct`, `adj_opp_tov_pct`, `adj_tov_edge` | Adjusted turnover % committed, forced, and edge | all | |
| `adj_orb_pct`, `adj_drb_pct`, `adj_reb_edge` | Adjusted offensive / defensive rebound % and edge | all | |
| `adj_ftr`, `adj_opp_ftr`, `adj_ftr_margin` | Adjusted free-throw rate for, against, and margin | all | |
| `ffi_adj` | Four Factor Index, 0–100 scale | all | Fixed weights 0.47 / 0.24 / 0.21 / 0.08 (shooting, turnovers, rebounding, free throws), not fitted |
| `wab` | Wins Above Bubble | all | Pre-tournament, D1-vs-D1 games |
| `wab_z` | `wab` standardized within season: (wab − season mean) / season std (population) | all | **Standardized within season**, so it compares a team to its own season, not across seasons |
| `sos_rank` | Strength-of-schedule rank among that season's D1 teams | all | **Pre-tournament** schedule only |
| `ap_poll_week6` | AP poll rank in week 6 (Sports-Reference) | all | NULL = unranked. Ties kept as published (2011, 2012, 2019, 2021), so a season can have 26–27 ranked teams |

### Shooting totals (pre-tournament team metrics)

| Column | Definition | Seasons | Caveats |
|---|---|---|---|
| `total_fg3m`, `total_fg3a`, `three_pt_pct` | Three-pointers made, attempted, and percentage | all | D1-vs-D1 games. Points-only box rows (frequent in 2005, 2012, 2013) add no attempts. |
| `total_ftm`, `total_fta`, `ft_pct` | Free throws made, attempted, and percentage | all | Same as above |

### D1 game features (`scripts/features/team_games.py`)

All D1-vs-D1, pre-cutoff, 0-0 excluded.

| Column | Definition | Seasons | Caveats |
|---|---|---|---|
| `d1_games`, `d1_wins`, `d1_losses` | Record against D1 opponents | all | **D1 only**, unlike `wins`/`losses` |
| `fga`, `fg3a`, `three_par` | Team field-goal and 3-point attempts, and 3PA / FGA | all | Box rows with FGA > 0 only |
| `opp_fga`, `opp_fg3a`, `opp_three_par` | The same for opponents | all | Same as above |
| `opp_box_coverage` | Share of games with a usable opponent box row | all | Below 1 mainly in 2005, 2012, 2013 (points-only rows) |
| `road_games`, `road_wins`, `road_win_pct` | True road games (away, not neutral) | 2008– | NULL 2005–2007: no neutral-site flags exist |
| `neutral_games`, `neutral_wins` | Neutral-site games | 2008– | NULL 2005–2007; 2026 flags are only partly right (see `location_quality`) |
| `location_quality` | `ok`, `partial` (2026), `none` (2005–2007) | all | |
| `last10_wins`, `last10_avg_margin` | Last 10 games before the cutoff, by tip time | all | |
| `close5_games`, `close5_wins` | Games decided by 5 points or fewer | all | |
| `ot_games`, `ot_wins` | Overtime games | all | Games with no period count are not counted (flagged `ot_period_unknown` in `data_issue`) |
| `q1_games`, `q1_wins` | Quad 1 games: opponent pre-tournament AdjEM rank ≤ 30 at home, ≤ 50 neutral, ≤ 75 away | 2008– | **A proxy on MacFax ranks**, not the NCAA's NET quadrants. NULL 2005–2007 (no location). |

### Roster continuity (`scripts/features/roster.py`)

Built from player-game rows (ESPN box scores), which exist from 2005. Continuity needs the prior season, so it
starts in 2006.

- **Names-only games.** For some older games ESPN's box score lists player names but no stats (about 12% of
  games in 2005, 2012 and 2013; a few percent in 2006–2007; under 1% in 2008–2011). Those games have no player
  rows. `player_data_games_pct` shows the share of a team's games with player rows. The missing games also count
  as misses in `min_closure_pct`, so many 2005, 2012 and 2013 teams are `partial`.
- **ncaa.com rows, 2023–2024.** In 2022–23 and 2023–24, players ESPN left out of its box scores (no name or stats)
  are filled from ncaa.com box scores (522 player-games, 21 team-seasons). They count as the team's players in
  every roster column. A filled player is linked to an ESPN player where MacFax has one; otherwise he is
  identified by exact name and team, so the same player in both seasons is a same-team returner (Robert Jones,
  Iowa St.). `ncaa_filled_min_pct` is the share of minutes from these rows.
- **2017–2022 gaps are not filled.** ESPN also left players out in 2018–2022 (and one Eastern Washington player
  in 2017), but ncaa.com box scores for those seasons weren't available, so those teams keep their gaps and are
  flagged `partial` or `poor` by `roster_quality`.

| Column | Definition | Seasons | Caveats |
|---|---|---|---|
| `team_min_obs` | Total pre-cutoff player minutes recorded | 2005– | |
| `min_closure_pct` | Share of pre-cutoff games whose player minutes sum to 200 + 25 per OT (± 5) | 2005– | Games without player rows count as misses |
| `roster_quality` | `ok` (closure ≥ 0.90), `partial` (≥ 0.50), `poor` | 2005– | Check this before trusting the roster columns |
| `ret_same_min_pct` | Share of minutes by players whose prior D1 team was this team | 2006– | Prior team = last D1 team in Y−1, else Y−2 |
| `transfer_min_pct` | Share of minutes by players whose prior D1 team was another team | 2006– | |
| `newcomer_min_pct` | Share of minutes by players with no D1 rows in Y−1 or Y−2 | 2006– | The three shares sum to 1 |
| `ret_prior_min_pct` | Share of last season's minutes (on this team) played by players back this season | 2006– | |
| `ret_same_pts_pct` | Share of points scored by same-team returners | 2006– | |
| `exp_prior_seasons` | Minutes-weighted mean number of prior seasons with D1 game rows | 2006– | Counts only seasons from 2005 on |
| `exp_censored` | True when the season is fewer than 4 years after 2005 | all | **Experience is censored before 2009**: a senior's earlier seasons can be missing |
| `roster_lookback_censored` | True when Y−2 has no player data (2006), False after | 2006– | **2006's Y−2 lookback hits 2004**, which has no player data, so sit-out and redshirt returners can look like newcomers |
| `ncaa_filled_min_pct` | Share of `team_min_obs` from ncaa.com rows | 2023–2024 | 0 for teams with nothing filled; NULL in other seasons (no fill attempted) |
| `player_data_games_pct` | Share of the team's pre-cutoff games with at least one player row | all | Below 1 mainly for names-only games, 2005–2013 |

### Data quality

| Column | Definition | Seasons | Caveats |
|---|---|---|---|
| `data_issue` | `;`-separated known, unfixed problems for that team-season; NULL = none known | all | Codes below |

`data_issue` codes:

- `player_omitted_espn`: Eastern Washington 2017; ESPN leaves one player out of every box score.
- `game_missing_vs_liu_2011`, `game_missing_vs_vermont_2011`: the Vermont–LIU game isn't stored (ESPN has
  only the first half), so both teams are one game short.
- `score_conflict_ncaa_espn`: three March 2026 games where NCAA and ESPN scores differ (NCAA's kept): SIU
  Edwardsville–Eastern Illinois, Belmont–Drake, Murray St.–Illinois Chicago.
- `box_points_short_game77`: Boston University and Northeastern 2026; one game's box rows total 2 points less
  than the score.
- `ot_period_unknown_<n>g`: n pre-cutoff games with no period count, so `ot_games` may undercount.
- `player_rows_incomplete_partial` / `_poor`: `roster_quality` is not `ok` (in 2005–2014 mostly names-only
  games; in 2017–2022 players ESPN left out).

### Modeling notes

- For a tournament-only model, filter to `made_tournament`.
- Outcome columns (`first_four` … `champion`) are labels, never predictors.
- Check `roster_quality`, `player_data_games_pct` and `data_issue` before using the roster columns, and use
  roster features only from 2007 (`roster_lookback_censored`) or 2009 (`exp_censored`) on if censoring matters.
- Many predictors are strongly correlated (the adjusted efficiency and four-factor columns especially). With 21
  champions, watch for overfitting.

### Reproduction (v3)

From the repo root, against the local `macfax` PostgreSQL database (read-only):

```
for f in team_games roster outcome; do
  PGOPTIONS='-c default_transaction_read_only=on' psql -d macfax -f scripts/features/${f}_extract.sql
done
PGOPTIONS='-c default_transaction_read_only=on' psql -d macfax -f scripts/export_base_v2.sql > data/interim/base.csv
.venv/bin/python scripts/features/team_games.py
.venv/bin/python scripts/features/roster.py
.venv/bin/python scripts/features/outcome.py
.venv/bin/python scripts/build_dataset.py
```

`build_dataset.py` stops with `CHECK FAILED` unless: one row per (season, team_id); one champion per season;
outcome closure holds (65/68 teams, 63 wins, 32/16/8/4/2/1 by round); roster shares sum to 1; no roster
continuity before 2006; and no feature is filled where its source is missing. Raw extracts in `data/raw/` are
gitignored.

### v2: `processed/champion_checklist_v2.csv`

Kept unchanged. Same rows and columns as v3 except: roster columns only from 2015 (continuity from 2016,
`exp_censored` relative to 2015, `roster_lookback_censored` True for 2016), no ncaa.com rows (18 of the 21 teams
filled in v3, Iowa St. among them, are `poor` or `partial` in v2; all 21 are `ok` in v3), and no `ncaa_filled_min_pct` or `player_data_games_pct`.

---

## v1: `processed/champion_checklist.csv`

The original export, kept for reference. One row per team-season with a pre-tournament rating row, 2005–2026
except 2020. Built by `scripts/export_champion_checklist.sql` from the local database `data5600_champions`.
It predates the MacFax data fixes (for example Boston College and Boston University merged, D1 meaning
"D1 today", missing AP ranks), so prefer v2. In v1, `champion` is 1/0 and `tournament_finish` (an outcome field)
records only Champion, Runner-Up and Final Four.

The original MacFax PostgreSQL backup is intentionally excluded from GitHub.
