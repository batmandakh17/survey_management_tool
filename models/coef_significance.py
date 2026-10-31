"""Standard errors, z, p and 95% intervals for the coefficients of the two bundled risk models.

The models are ridge-penalised logistic regressions with one intercept per program (train_risk.py). They are refitted
here on the same local tables, and checked against models/risk_models.json. Standard errors come from the sandwich
estimator of that penalised fit, with households as clusters: a household contributes several household-rounds, which
are not independent. An unpenalised refit is reported beside each coefficient, to show what the small penalty changes.

Run from the tool folder:  python3 models/coef_significance.py
Reads country_experience/_handbook_work/ (local, unpublished). Writes only aggregates: models/coefficients.json.
"""
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import train_risk as T  # noqa: E402


def cluster_fit(X, y, groups, clusters, lam):
    """The penalised fit (train_risk.fit_logit) and its cluster-robust covariance, H^-1 B H^-1."""
    m = T.fit_logit(X, y, groups, lam=lam)
    G = sorted(set(groups))
    gi = np.array([G.index(g) for g in groups])
    Z = np.zeros((len(y), len(G)))
    Z[np.arange(len(y)), gi] = 1.0
    A = np.hstack([Z, X])
    w = np.r_[[m["intercepts"][g] for g in G], m["coef"]]
    p = 1 / (1 + np.exp(-(A @ w)))
    pen = np.r_[np.zeros(len(G)), np.full(X.shape[1], lam)]
    H = (A * (p * (1 - p))[:, None]).T @ A + np.diag(pen)
    codes, uniq = pd.factorize(pd.Series(clusters))
    S = np.zeros((len(uniq), A.shape[1]))
    np.add.at(S, codes, A * (y - p)[:, None])
    nc, n, k = len(uniq), len(y), A.shape[1]
    B = S.T @ S * (nc / (nc - 1)) * ((n - 1) / (n - k))       # the usual small-sample correction for clustered errors
    Hi = np.linalg.inv(H)
    V = Hi @ B @ Hi
    se = np.sqrt(np.diag(V))[len(G):]
    return m, se, nc


def table(df, feats, labels, lam, bundled):
    st = T.standardise(df, feats)
    X = T.design(df, feats, st)
    y = df["y"].astype(float).values
    groups = df["program"].values
    clusters = (df["program"].astype(str) + "|" + df["hhid"].astype(str)).values
    m, se, nc = cluster_fit(X, y, groups, clusters, lam)
    m0 = T.fit_logit(X, y, groups, lam=0.0)
    drift = float(np.max(np.abs(m["coef"] - np.array([f["coef"] for f in bundled["features"]]))))
    rows = []
    for j, k in enumerate(feats):
        b, s = float(m["coef"][j]), float(se[j])
        z = b / s if s > 0 else float("nan")
        rows.append({"key": k, "label": labels[k], "coef": round(b, 4), "se": round(s, 4), "z": round(z, 2),
                     "p": float(f"{math.erfc(abs(z) / math.sqrt(2)):.3g}"), "ci_lo": round(b - 1.96 * s, 4), "ci_hi": round(b + 1.96 * s, 4),
                     "odds_ratio_per_sd": round(math.exp(b), 3), "coef_unpenalised": round(float(m0["coef"][j]), 4)})
    return {"n": int(len(y)), "households": int(nc), "programs": sorted(set(groups)), "events": int(y.sum()),
            "max_difference_from_bundled_model": round(drift, 6), "features": rows}


def main():
    t0 = time.time()
    M = json.load(open(os.path.join(HERE, "risk_models.json")))
    D, R = [], []
    for c in T.PROGRAMS:
        d, r, _ = T.build_pairs(c)
        D.append(d)
        if r is not None:
            R.append(r)
    D, R = pd.concat(D, ignore_index=True), pd.concat(R, ignore_index=True)
    D["program"] = D["program"].map(T.LABEL)
    R["program"] = R["program"].map(T.LABEL)
    out = {"schema": "rtm-coefficients-1.0", "computed_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "lambda": T.LAMBDA,
           "method": ("Ridge-penalised logistic regression with one intercept per program, refitted on the training tables; "
                      "sandwich standard errors with households as clusters (small-sample corrected); z = coefficient / SE; "
                      "two-sided p from the normal distribution. Coefficients are per standard deviation of the feature."),
           "dropout": table(D, [k for k, _, _ in T.DROP_FEATURES], {k: l for k, l, _ in T.DROP_FEATURES}, T.LAMBDA, M["dropout"]),
           "return": table(R, [k for k, _, _ in T.RET_FEATURES], {k: l for k, l, _ in T.RET_FEATURES}, T.LAMBDA, M["return"])}
    json.dump(out, open(os.path.join(HERE, "coefficients.json"), "w"), indent=1)
    for kind in ("dropout", "return"):
        x = out[kind]
        print(f"{kind}: {x['n']} household-rounds, {x['households']} households, refit differs from the bundled model by {x['max_difference_from_bundled_model']}")
        for f in x["features"]:
            print(f"  {f['coef']:+.3f} ({f['ci_lo']:+.3f} to {f['ci_hi']:+.3f})  z {f['z']:6.2f}  p {f['p']:.2g}  {f['label']}")
    print(f"written models/coefficients.json in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
