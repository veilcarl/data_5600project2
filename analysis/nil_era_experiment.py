"""Exploratory NIL-era walk-forward comparison for NCAA Crystal Ball v3.
This is research conducted AFTER viewing the 2022-2026 holdout; do not present
as an untouched holdout or causal test of NIL effects.
"""
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.decomposition import PCA
from sklearn.pipeline import Pipeline

DATA = next((p for p in [
    Path('data/processed/champion_checklist_v3.csv'),
    Path('../data/processed/champion_checklist_v3.csv'),
    Path('/mnt/data/champion_checklist_v3.csv'),
] if p.exists()), None)
if DATA is None:
    raise FileNotFoundError('Run from the repo root, with data/processed/champion_checklist_v3.csv available')
OUTPUT_DIR = Path('analysis') if Path('analysis').is_dir() else Path('.')
d = pd.read_csv(DATA)
d=d.loc[(~d['is_reclassifying']) & d.season.between(2009,2026)].copy()
d['y']=d['champion'].eq(True).astype(int)
base=['adj_em','wab_z','sos_rank']
roster=base+['ret_same_min_pct','transfer_min_pct','ret_prior_min_pct','exp_prior_seasons']
curated=['adj_o','adj_d','adj_em','adj_tempo','adj_efg_pct','adj_opp_efg_pct','adj_tov_pct','adj_opp_tov_pct','adj_orb_pct','adj_drb_pct','adj_ftr','adj_opp_ftr','ffi_adj','wab_z','sos_rank','win_pct','three_pt_pct','ft_pct','three_par','opp_three_par','last10_wins','last10_avg_margin','road_win_pct','q1_wins','ret_same_min_pct','transfer_min_pct','ret_prior_min_pct','exp_prior_seasons']
wide=['games_played','wins','losses','win_pct','adj_o','adj_d','adj_em','adj_tempo','rank_adj_o','rank_adj_d','rank_adj_em','adj_efg_pct','adj_opp_efg_pct','adj_efg_margin','adj_tov_pct','adj_opp_tov_pct','adj_tov_edge','adj_orb_pct','adj_drb_pct','adj_reb_edge','adj_ftr','adj_opp_ftr','adj_ftr_margin','ffi_adj','wab','wab_z','sos_rank','total_fg3m','total_fg3a','three_pt_pct','total_ftm','total_fta','ft_pct','d1_games','d1_wins','d1_losses','fga','fg3a','three_par','opp_fga','opp_fg3a','opp_three_par','road_games','road_wins','road_win_pct','neutral_games','neutral_wins','last10_wins','last10_avg_margin','close5_games','close5_wins','ot_games','ot_wins','q1_games','q1_wins','ret_same_min_pct','transfer_min_pct','newcomer_min_pct','ret_prior_min_pct','ret_same_pts_pct','exp_prior_seasons']

def make_model(C=3, n_pc=None):
    return Pipeline([('impute',SimpleImputer(strategy='median')),('scale',StandardScaler())] +
                    ([('pca',PCA(n_components=n_pc,svd_solver='full'))] if n_pc else []) +
                    [('model',LogisticRegression(C=C,solver='lbfgs',max_iter=3000))])

strategies=[
    ('Baseline, expanding history', base, 3, None, None, 2009),
    ('Baseline, frozen pre-2022', base, 3, None, None, 2009),
    ('Baseline, half-life 4 yrs', base, 3, None, 4, 2009),
    ('Baseline, half-life 8 yrs', base, 3, None, 8, 2009),
    ('Baseline, recent 5 seasons', base, 3, None, None, 'last5'),
    ('Roster, expanding history',roster,3,None,None,2009),
    ('Roster, half-life 4 yrs',roster,3,None,4,2009),
    ('Roster, NIL-only',roster,3,None,None,2022),
    ('Baseline, NIL-only',base,3,None,None,2022),
    ('PCA28 (5 PCs), expanding',curated,3,5,None,2009),
    ('PCA61 (5 PCs), expanding',wide,3,5,None,2009),
    ('Ridge28, expanding',curated,0.3,None,None,2009),
]
rows=[]
for year in range(2022,2027):
    g=d[d.season==year].copy()
    for name,cols,C,n_pc,half_life,first in strategies:
        if first == 'last5':
            seasons = sorted(s for s in d.season.unique() if s<year)[-5:]
            tr=d[d.season.isin(seasons)].copy()
        else:
            tr=d[(d.season<year)&(d.season>=first)].copy()
        if name=='Baseline, frozen pre-2022': tr=tr[tr.season<=2021]
        if tr.y.sum()<1: continue
        m=make_model(C=C,n_pc=n_pc)
        fit_extra={}
        if half_life:
            age=(year-1-tr.season).to_numpy()
            w=0.5**(age/half_life)
            fit_extra['model__sample_weight']=w
        m.fit(tr[cols],tr.y,**fit_extra)
        prob=m.predict_proba(g[cols])[:,1]
        # normalize across one winner each tournament
        prob=np.clip(prob,1e-15,None); p_norm=prob/prob.sum()
        chp=int(np.flatnonzero(g.y.to_numpy()==1)[0])
        rank=int((prob>prob[chp]).sum()+1)
        rows.append({'year':year,'strategy':name,'trained_years':tr.season.nunique(), 'train_champions':int(tr.y.sum()),'champion_team':g.iloc[chp].team,'winner_rank':rank,'winner_share':p_norm[chp],'winner_logloss':-np.log(p_norm[chp])})

r=pd.DataFrame(rows)
r.to_csv(OUTPUT_DIR / 'nil_walk_forward_predictions.csv',index=False)
out=[]
for name,g in r.groupby('strategy',sort=False):
    out.append({'strategy':name,'years_evaluated':len(g),'avg_winner_logloss':g.winner_logloss.mean(),'top5':sum(g.winner_rank<=5),'top10':sum(g.winner_rank<=10),'mean_rank':g.winner_rank.mean(),'ranks':','.join(map(str,g.sort_values('year').winner_rank)),'scores':','.join(f'{x:.2f}' for x in g.sort_values('year').winner_logloss)})
summ=pd.DataFrame(out).sort_values('avg_winner_logloss')
summ.to_csv(OUTPUT_DIR / 'nil_walk_forward_summary.csv',index=False)
print('\nWalk-forward (2022–2026, where applicable):')
print(summ.to_string(index=False,formatters={'avg_winner_logloss':'{:.4f}'.format,'mean_rank':'{:.1f}'.format}))
print('\nPer-season winner log loss:')
print(r.pivot(index='year',columns='strategy',values='winner_logloss').round(3).to_string())
print('\nPer-season champion ranks:')
print(r.pivot(index='year',columns='strategy',values='winner_rank').to_string())
