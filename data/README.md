# NCAA Champion Checklist — DATA 5600

## Shared dataset
`processed/champion_checklist.csv`

One row represents one NCAA team in one historical season.

## Coverage
- Seasons: 2005–2026
- Excludes 2020 (NCAA tournament canceled)
- Uses pre-tournament team ratings and metrics
- Includes both tournament and non-tournament teams

## Important columns
- `season`: Ending year of the season
- `team`: Team name
- `made_tournament`: Whether the team received a tournament seed
- `tournament_seed`: Tournament seed, if applicable
- `champion`: 1 for national champions, 0 otherwise
- `adj_o`, `adj_d`, `adj_em`: Adjusted efficiency metrics
- `ffi_adj`: Adjusted Four Factor Index
- `wab`: Wins Above Bubble
- Other columns: Shooting, rebounding, turnover and ranking measures

## Modeling notes
For a tournament-only model, filter to made_tournament = true.

`tournament_finish` is an outcome field, not an eligible
pre-tournament predictor.

Avoid using all predictors simultaneously without considering
multicollinearity, sparse positive outcomes and overfitting.

## Reproduction
`scripts/export_champion_checklist.sql` generates the CSV from
the local PostgreSQL database `data5600_champions`.

The original MacFax PostgreSQL backup is intentionally excluded
from GitHub.
