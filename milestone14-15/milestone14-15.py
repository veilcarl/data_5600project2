
import numpy as np
import pandas as pd
import statsmodels.api as sm
import matplotlib.pyplot as plt
from statsmodels.stats.outliers_influence import variance_inflation_factor

# ------------------------------------------------------------------
# 0. CONFIG: edit these
# ------------------------------------------------------------------
PATH = "/Users/trumanwells/data_5600project2/data/processed/champion_checklist.csv"
TARGET = "adj_em"                  # outcome column
POSITIVE_CLASS = "tournament_finish"      # coded as 1; everything else coded as 0
PREDICTORS = None                 # e.g. ["age", "score", "source"]; None = use all other columns
DROP_COLS = []                    # ID-like columns to exclude, e.g. ["lead_id"]

# ------------------------------------------------------------------
# 1. LOAD + MINIMAL PREP (no cleaning, just what statsmodels needs)
# ------------------------------------------------------------------
df = pd.read_csv(PATH)
df = df[df[TARGET].isin([POSITIVE_CLASS] + [v for v in df[TARGET].unique() if v != POSITIVE_CLASS])]
y = (df[TARGET] == POSITIVE_CLASS).astype(int)

cols = PREDICTORS or [c for c in df.columns if c != TARGET and c not in DROP_COLS]
X_raw = df[cols].copy()

num_cols = X_raw.select_dtypes(include="number").columns.tolist()
cat_cols = [c for c in X_raw.columns if c not in num_cols]

X = pd.get_dummies(X_raw, columns=cat_cols, drop_first=True)
X = X.astype(float)

# statsmodels can't fit with NaN/inf, so drop only the rows that block fitting
X = X.replace([np.inf, -np.inf], np.nan)
keep = X.notna().all(axis=1) & y.notna()
X, y = X[keep], y[keep]
print(f"Rows used: {len(X)} of {len(df)} | predictors after encoding: {X.shape[1]}")

# ------------------------------------------------------------------
# 2. ASSUMPTION 1: Binary outcome + sufficient sample size
# ------------------------------------------------------------------
print("\n=== ASSUMPTION 1: Binary outcome & sample size ===")
counts = y.value_counts()
print(counts.rename({1: POSITIVE_CLASS, 0: "Other"}))
events = counts.min()
epv = events / X.shape[1]
print(f"Events per predictor (smaller class / # predictors): {epv:.1f}  (rule of thumb: >= 10)")

# ------------------------------------------------------------------
# 3. ASSUMPTION 2: Independence of observations
#    (can't be tested directly; check for duplicate rows / repeated IDs)
# ------------------------------------------------------------------
print("\n=== ASSUMPTION 2: Independence ===")
print(f"Duplicate rows in predictors: {X.duplicated().sum()}")
print("Check study design too: repeated leads/contacts or clustering would violate this.")

# ------------------------------------------------------------------
# 4. ASSUMPTION 3: No severe multicollinearity (VIF)
# ------------------------------------------------------------------
print("\n=== ASSUMPTION 3: Multicollinearity (VIF) ===")
Xc = sm.add_constant(X)
vif = pd.DataFrame({
    "variable": Xc.columns,
    "VIF": [variance_inflation_factor(Xc.values, i) for i in range(Xc.shape[1])],
}).query("variable != 'const'").sort_values("VIF", ascending=False)
print(vif.to_string(index=False))
print("Rule of thumb: VIF > 5 is concerning, > 10 is severe.")

# ------------------------------------------------------------------
# 5. FIT THE MODEL -> PARAMETER ESTIMATES
# ------------------------------------------------------------------
print("\n=== PARAMETER ESTIMATES (Logit, MLE) ===")
logit = sm.Logit(y, Xc).fit(disp=False)
print(logit.summary())

ci = logit.conf_int()
est = pd.DataFrame({
    "coef (log-odds)": logit.params,
    "std err": logit.bse,
    "z": logit.tvalues,
    "p-value": logit.pvalues,
    "odds ratio": np.exp(logit.params),
    "OR 2.5%": np.exp(ci[0]),
    "OR 97.5%": np.exp(ci[1]),
})
print("\nCoefficients and odds ratios:")
print(est.round(4).to_string())
print(f"\nPseudo R^2 (McFadden): {logit.prsquared:.4f} | AIC: {logit.aic:.1f} | LLR p-value: {logit.llr_pvalue:.4g}")

# ------------------------------------------------------------------
# 6. ASSUMPTION 4: Linearity of the logit for continuous predictors (Box-Tidwell)
#    Add x*ln(x) terms; a significant interaction term suggests nonlinearity
# ------------------------------------------------------------------
print("\n=== ASSUMPTION 4: Linearity of the logit (Box-Tidwell) ===")
cont = [c for c in num_cols if c in X.columns and X[c].nunique() > 2]
if cont:
    X_bt = Xc.copy()
    bt_terms = []
    for c in cont:
        shifted = X[c] - X[c].min() + 1          # Box-Tidwell needs strictly positive values
        name = f"{c}:ln({c})"
        X_bt[name] = shifted * np.log(shifted)
        bt_terms.append(name)
        X_bt[c] = shifted                         # use the shifted version so terms are consistent
    bt = sm.Logit(y, X_bt).fit(disp=False)
    bt_tbl = pd.DataFrame({"coef": bt.params[bt_terms], "p-value": bt.pvalues[bt_terms]})
    bt_tbl["nonlinear? (p<0.05, Bonferroni)"] = bt_tbl["p-value"] < (0.05 / len(bt_terms))
    print(bt_tbl.round(4).to_string())

    # Visual check: binned empirical logit vs predictor
    n = len(cont)
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 4), squeeze=False)
    for ax, c in zip(axes[0], cont):
        bins = pd.qcut(X[c], q=10, duplicates="drop")
        g = pd.DataFrame({"x": X[c], "y": y}).groupby(bins, observed=True).agg(x=("x", "mean"), p=("y", "mean"))
        p = g["p"].clip(0.001, 0.999)
        ax.plot(g["x"], np.log(p / (1 - p)), "o-")
        ax.set_xlabel(c)
        ax.set_ylabel("empirical logit")
        ax.set_title(f"Logit linearity: {c}")
    plt.tight_layout()
    plt.show()
else:
    print("No continuous predictors found; assumption not applicable.")

# ------------------------------------------------------------------
# 7. ASSUMPTION 5: No highly influential outliers (Cook's D, standardized residuals)
# ------------------------------------------------------------------
print("\n=== ASSUMPTION 5: Influential observations ===")
glm = sm.GLM(y, Xc, family=sm.families.Binomial()).fit()
infl = glm.get_influence()
cooks = infl.cooks_distance[0]
std_resid = glm.resid_pearson / np.sqrt(1 - infl.hat_matrix_diag)

thresh = 4 / len(y)
print(f"Cook's D > 4/n ({thresh:.5f}): {(cooks > thresh).sum()} observations")
print(f"Max Cook's D: {cooks.max():.4f} (values > 1 are clearly problematic)")
print(f"|Standardized residual| > 3: {(np.abs(std_resid) > 3).sum()} observations")

fig, ax = plt.subplots(1, 2, figsize=(12, 4))
ax[0].stem(np.arange(len(cooks)), cooks, markerfmt=",", basefmt=" ")
ax[0].axhline(thresh, color="red", ls="--", label="4/n")
ax[0].set(title="Cook's distance", xlabel="observation", ylabel="Cook's D")
ax[0].legend()
ax[1].scatter(glm.fittedvalues, std_resid, s=8, alpha=0.5)
ax[1].axhline(3, color="red", ls="--")
ax[1].axhline(-3, color="red", ls="--")
ax[1].set(title="Standardized residuals vs fitted", xlabel="fitted probability", ylabel="std Pearson residual")
plt.tight_layout()
plt.show()

# ------------------------------------------------------------------
# 8. EXTRA: separation / convergence check
# ------------------------------------------------------------------
print("\n=== EXTRA: Convergence / separation check ===")
print(f"Converged: {logit.mle_retvals['converged']}")
print("Huge coefficients/standard errors (|coef| > 10) can signal (quasi-)complete separation:")
print(est.loc[est["coef (log-odds)"].abs() > 10, ["coef (log-odds)", "std err"]])

