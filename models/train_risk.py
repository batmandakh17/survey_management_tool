"""Train and backtest the two risk models of PROPOSAL.md section E, locally, on the handbook's harmonised tables.

  Dropout risk:      a household interviewed in round t; target 1 = not interviewed in round t+1 (the handbook's loss).
  Return likelihood: a household interviewed in t and missed in t+1; target 1 = interviewed again in t+2, t+3 or t+4.

Interviewed = a completed call-log case, as the handbook's build script defines it (10_build_attempts.py). Features are
operational only (D8) and use only what is known before the round predicted. Data: the six dial-log programs' case and
dial tables in country_experience/_handbook_work/ (local, unpublished). Writes only coefficients and validation
aggregates, with no household ID and with cells under 10 suppressed:
  models/risk_models.json     what the tool bundles: features, coefficients, intercepts, tiers, model card
  models/validation.json      every backtest table
Run:  python3 models/train_risk.py
"""
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, "..", "..", "..", "country_experience", "_handbook_work"))
PROGRAMS = ["UZB", "TAJ", "KGZ", "KAZ", "PHL", "IND"]
LABEL = {"UZB": "L2CU", "TAJ": "L2T", "KGZ": "L2KGZ", "KAZ": "L2Kaz", "PHL": "L2PHL", "IND": "L2Indo"}
RETURN_PROGRAMS = ["PHL", "IND"]          # they redial almost every missed household (3.3.5)
MIN_CELL = 10
TIERS = (0.15, 0.35)                      # top 15% high, next 35% medium, the rest low (D7)
LAMBDA = 1.0
rng = np.random.default_rng(20261027)

# Result codes onto categories. None = the program's codes do not define the category (TAJ and KGZ, as the handbook says).
CODES = {
    "UZB": {"number": {"Non-working number", "Wrong number", "Out of Service Area"}, "refusal": None,
            "contact": {"No time", "Interrapted survey", "Hangup"}},
    "TAJ": {"number": None, "refusal": None, "contact": None},
    "KGZ": {"number": None, "refusal": None, "contact": None},
    "KAZ": {"number": {"Disconnected number", "Business, government office, other organization"}, "refusal": {"Soft Refusal, Respondent"},
            "contact": {"Call again", "Definite Appointment - Respondent", "Not available", "Other, Referred to Supervisor (Eligible)"}},
    "PHL": {"number": {"Number does not exist / Not ringing", "Phone off / Not in service", "Don't know the household"}, "refusal": {"Refused"},
            "contact": {"Not yet started (scheduled call)", "Partially complete (scheduled call)", "Partially complete (no more call)"}},
    "IND": {"number": {"Failed (no dial tone/silent, voice mail, wrong number)", "Not match with data base", "NOMER TIDAK AKTIF /TIDAK ADA WA"},
            "refusal": {"Refused to participate"},
            "contact": {"On Appointment", "ON APPOINTMENT", "Partially Completed Interviews", "Partially complete interviews"}},
}
# the tool's own codes onto the same categories (written into risk_models.json for the browser)
TOOL_CODES = {"number": ["DEAD_NUMBER", "WRONG_NUMBER", "SWITCHED_OFF"], "refusal": ["REFUSAL_SOFT", "REFUSAL_HARD"],
              "contact": ["APPOINTMENT", "PARTIAL", "NOT_AVAILABLE", "LANGUAGE", "OTHER"]}

TENURE_BINS = [(1, 1, "k1"), (2, 2, "k2"), (3, 3, "k3"), (4, 6, "k4_6"), (7, 12, "k7_12"), (13, 10 ** 6, "k13p")]
TENURE_REF = "k4_6"
DROP_FEATURES = [
    ("k1", "Joined in the round before", "tenure"), ("k2", "Joined two rounds before", "tenure"), ("k3", "Joined three rounds before", "tenure"),
    ("k7_12", "In the panel 7 to 12 rounds", "tenure"), ("k13p", "In the panel 13 rounds or more", "tenure"),
    ("missed_prev", "Rounds missed among the three before", "history"), ("missed_t1", "Missed the round before", "history"),
    ("dials_needed", "Dials needed last round (log)", "effort"), ("days_needed", "Days needed last round", "effort"),
    ("same_enum", "Same enumerator in the last two interviews", "continuity"), ("first_within_hour", "Last round's first dial within an hour of the interview before", "timing"),
    ("hour_evening", "Last interview at 18:00 or later", "timing"), ("hour_morning", "Last interview before 12:00", "timing"),
    ("interview_min", "Length of the last interview (minutes)", "effort"),
    ("number_problem", "A number not working or switched off last round", "numbers"), ("refusal", "A refusal last round before the interview", "refusal"),
]
RET_FEATURES = [
    ("k1", "Joined in the round before the miss", "tenure"), ("k2", "Joined two rounds before the miss", "tenure"), ("k3", "Joined three rounds before the miss", "tenure"),
    ("k7_12", "In the panel 7 to 12 rounds", "tenure"), ("k13p", "In the panel 13 rounds or more", "tenure"),
    ("missed_prev", "Rounds missed among the three before the last interview", "history"),
    ("dialled_miss", "Dialed in the missed round", "effort"), ("dials_miss", "Dials in the missed round (log)", "effort"), ("days_miss", "Days dialed in the missed round", "effort"),
    ("contact_miss", "Reached in the missed round, no interview", "contact"), ("refusal_miss", "A refusal in the missed round", "refusal"),
    ("number_problem_miss", "A number not working or switched off in the missed round", "numbers"),
    ("dials_needed", "Dials needed at the last interview (log)", "effort"), ("same_enum_miss", "Missed round first dialed by the enumerator of the last interview", "continuity"),
]


# explanations add up the contributions of related features and describe the household's own values
DROP_GROUPS = [
    ("tenure", "Rounds since joining", ["k1", "k2", "k3", "k7_12", "k13p"]),
    ("history", "Rounds missed before the last interview", ["missed_prev", "missed_t1"]),
    ("effort", "Effort the last interview needed", ["dials_needed", "days_needed"]),
    ("continuity", "Enumerator of the last two interviews", ["same_enum"]),
    ("timing", "Time of the last interview", ["first_within_hour", "hour_evening", "hour_morning"]),
    ("length", "Length of the last interview", ["interview_min"]),
    ("numbers", "Numbers not working last round", ["number_problem"]),
    ("refusal", "A refusal last round", ["refusal"]),
]
RET_GROUPS = [
    ("tenure", "Rounds since joining", ["k1", "k2", "k3", "k7_12", "k13p"]),
    ("history", "Rounds missed before the last interview", ["missed_prev"]),
    ("miss_effort", "Effort in the missed round", ["dialled_miss", "dials_miss", "days_miss"]),
    ("contact", "Reached in the missed round", ["contact_miss"]),
    ("refusal", "A refusal in the missed round", ["refusal_miss"]),
    ("numbers", "Numbers not working in the missed round", ["number_problem_miss"]),
    ("effort", "Effort the last interview needed", ["dials_needed"]),
    ("continuity", "Missed round first dialed by the enumerator of the last interview", ["same_enum_miss"]),
]


def norm_op(s):
    return str(s).strip().replace("_", "").upper() if s is not None and str(s).strip() not in ("", "nan", "None") else ""


# ------------------------------------------------------------------ features
def load(c):
    ca = pd.read_pickle(os.path.join(WORK, f"cases_{c}.pkl"))
    di = pd.read_pickle(os.path.join(WORK, f"dials_{c}.pkl"))
    ca = ca[["hhid", "round", "n_att", "n_days", "k_complete", "completed", "day_complete"]].copy()
    keep = ["hhid", "round", "ts", "status_raw", "dur_min", "operator", "attempt", "k_complete"] + (["time_known"] if "time_known" in di.columns else [])
    di = di[keep].copy()
    di["hhid"] = di["hhid"].astype(str)
    ca["hhid"] = ca["hhid"].astype(str)
    return ca, di


def case_facts(codes, ca, di):
    """Per case: the completing dial (time, operator, length), the first dial, and disposition flags of its dials."""
    s = di["status_raw"].astype(str).str.strip()
    di["is_number"] = s.isin(codes["number"]) if codes["number"] is not None else False
    di["is_refusal"] = s.isin(codes["refusal"]) if codes["refusal"] is not None else False
    di["is_contact"] = s.isin(codes["contact"]) if codes["contact"] is not None else False
    di["hour"] = di["ts"].dt.hour.astype(float)
    di["minute"] = di["ts"].dt.minute.astype(float)
    if "time_known" in di.columns:
        unk = ~di["time_known"].astype(bool)
        di.loc[unk, "hour"] = np.nan
        di.loc[unk, "minute"] = np.nan
    di["op"] = di["operator"].map(norm_op)
    key = ["hhid", "round"]
    cmp = di[di["attempt"] == di["k_complete"]][key + ["hour", "minute", "op", "dur_min"]].rename(columns={"hour": "c_hour", "minute": "c_min", "op": "c_op", "dur_min": "c_dur"})
    first = di[di["attempt"] == 1][key + ["hour", "minute", "op"]].rename(columns={"hour": "f_hour", "minute": "f_min", "op": "f_op"})
    pre = di[~(di["attempt"] == di["k_complete"])]                     # every dial but the completing one
    flags = pre.groupby(key).agg(any_number=("is_number", "max"), any_refusal=("is_refusal", "max"), any_contact=("is_contact", "max")).reset_index()
    f = ca.merge(cmp, on=key, how="left").merge(first, on=key, how="left").merge(flags, on=key, how="left")
    for col in ("any_number", "any_refusal", "any_contact"):
        f[col] = f[col].fillna(False).astype(bool)
    return f


def tenure_dummies(k):
    out = {}
    for lo, hi, name in TENURE_BINS:
        if name != TENURE_REF:
            out[name] = ((k >= lo) & (k <= hi)).astype(float)
    return out


def circ_gap(h1, m1, h2, m2):
    d = np.abs((h1 + m1 / 60) - (h2 + m2 / 60))
    return np.minimum(d, 24 - d)


def build_pairs(c):
    ca, di = load(c)
    return pairs_from_tables(ca, di, CODES[c], c, c in RETURN_PROGRAMS)


def pairs_from_tables(ca, di, codes, c, with_return, require_outcome=True):
    """Feature rows from harmonised case and dial tables. With require_outcome=False, rows whose outcome round is not yet in
    the data are kept too (y is then missing): the rows a tool scores at the start of a round."""
    f = case_facts(codes, ca, di)
    rounds = sorted(f["round"].unique())
    rset = set(rounds)
    last = max(rounds)
    done = set(zip(f.loc[f["completed"], "hhid"], f.loc[f["completed"], "round"]))
    entry = f[f["completed"]].groupby("hhid")["round"].min()
    f = f.join(entry.rename("entry"), on="hhid")
    idx = f.set_index(["hhid", "round"])
    avail_number = codes["number"] is not None
    avail_refusal = codes["refusal"] is not None
    avail_contact = codes["contact"] is not None
    has_len = f["c_dur"].notna().any()

    def missed_prev(h, t, e):
        n = 0
        for j in (1, 2, 3):
            r = t - j
            if r in rset and r >= e and (h, r) not in done:
                n += 1
        return n

    # ---- dropout pairs: completed in t, round t+1 in the data
    D = f[f["completed"] & f["round"].map(lambda r: (r + 1) in rset or not require_outcome)].copy()
    D["y"] = [((h, t + 1) not in done) if (t + 1) in rset else np.nan for h, t in zip(D["hhid"], D["round"])]
    D["k"] = D["round"] + 1 - D["entry"]
    D["missed_prev"] = [missed_prev(h, t, e) for h, t, e in zip(D["hhid"], D["round"], D["entry"])]
    D["missed_t1"] = [float((t - 1) in rset and (t - 1) >= e and (h, t - 1) not in done) for h, t, e in zip(D["hhid"], D["round"], D["entry"])]
    D["dials_needed"] = np.log1p(np.minimum(D["k_complete"].astype(float), 20))
    D["days_needed"] = np.minimum(D["day_complete"].astype(float), 10)
    pk = list(zip(D["hhid"], D["round"] - 1))
    P = idx.reindex(pk)[["c_hour", "c_min", "c_op", "completed"]].reset_index(drop=True)
    prev_ok = P["completed"].fillna(False).astype(bool).values
    D["same_enum"] = np.where(prev_ok & (D["c_op"].values != "") & (D["c_op"].values == P["c_op"].fillna("").values), 1.0, 0.0)
    gap = circ_gap(D["f_hour"].values, D["f_min"].values, P["c_hour"].values, P["c_min"].values)
    D["first_within_hour"] = np.where(prev_ok & ~np.isnan(gap) & (gap <= 1), 1.0, 0.0)
    D["hour_known"] = D["c_hour"].notna()
    D["hour_evening"] = np.where(D["hour_known"], (D["c_hour"] >= 18).astype(float), np.nan)
    D["hour_morning"] = np.where(D["hour_known"], (D["c_hour"] < 12).astype(float), np.nan)
    D["interview_min"] = np.where(D["c_dur"].notna(), np.clip(D["c_dur"].astype(float), 0, 120), np.nan) if has_len else np.nan
    D["number_problem"] = D["any_number"].astype(float) if avail_number else np.nan
    D["refusal"] = D["any_refusal"].astype(float) if avail_refusal else np.nan
    for k_, v in tenure_dummies(D["k"]).items():
        D[k_] = v
    D["program"] = c

    # ---- return pairs: completed in t, missed in t+1, with t+4 in the data
    R = None
    if with_return:
        R = f[f["completed"] & f["round"].map(lambda r: (r + 1) in rset and (r + 4 <= last or not require_outcome))].copy()
        R = R[[(h, t + 1) not in done for h, t in zip(R["hhid"], R["round"])]].copy()
        R["y"] = [any((h, t + j) in done for j in (2, 3, 4)) if t + 4 <= last else np.nan for h, t in zip(R["hhid"], R["round"])]
        R["k"] = R["round"] + 1 - R["entry"]
        R["missed_prev"] = [missed_prev(h, t, e) for h, t, e in zip(R["hhid"], R["round"], R["entry"])]
        mk = list(zip(R["hhid"], R["round"] + 1))
        Mx = idx.reindex(mk)[["n_att", "n_days", "any_contact", "any_refusal", "any_number", "f_op"]].reset_index(drop=True)
        dialled = Mx["n_att"].notna().values
        R["dialled_miss"] = dialled.astype(float)
        R["dials_miss"] = np.log1p(np.minimum(Mx["n_att"].fillna(0).astype(float).values, 20))
        R["days_miss"] = np.minimum(Mx["n_days"].fillna(0).astype(float).values, 10)
        R["contact_miss"] = Mx["any_contact"].fillna(False).astype(float).values if avail_contact else np.nan
        R["refusal_miss"] = Mx["any_refusal"].fillna(False).astype(float).values if avail_refusal else np.nan
        R["number_problem_miss"] = Mx["any_number"].fillna(False).astype(float).values if avail_number else np.nan
        R["dials_needed"] = np.log1p(np.minimum(R["k_complete"].astype(float), 20))
        R["same_enum_miss"] = np.where(dialled & (R["c_op"].values != "") & (Mx["f_op"].fillna("").values == R["c_op"].values), 1.0, 0.0)
        for k_, v in tenure_dummies(R["k"]).items():
            R[k_] = v
        R["program"] = c
    meta = {"rounds": len(rounds), "first_round": int(rounds[0]), "last_round": int(last), "cases": int(len(f)), "completed": int(f["completed"].sum()),
            "available": {"number": avail_number, "refusal": avail_refusal, "contact": avail_contact, "length": bool(has_len),
                          "hour": bool(D["hour_known"].any())}}
    return D, R, meta


# ------------------------------------------------------------------ models
def standardise(df, feats):
    """Means and SDs over rows where the feature is available; an unavailable value becomes the mean (contributes nothing)."""
    st = {}
    for k in feats:
        v = df[k].astype(float).values
        ok = ~np.isnan(v)
        m = float(v[ok].mean()) if ok.any() else 0.0
        sd = float(v[ok].std()) if ok.any() else 1.0
        st[k] = (m, sd if sd > 1e-9 else 1.0)
    return st


def design(df, feats, st):
    X = np.empty((len(df), len(feats)))
    for j, k in enumerate(feats):
        v = df[k].astype(float).values
        m, sd = st[k]
        X[:, j] = np.where(np.isnan(v), 0.0, (v - m) / sd)
    return X


def fit_logit(X, y, groups, lam=LAMBDA, iters=50):
    """Ridge-penalised logistic regression with one unpenalised intercept per group (program), by Newton's method."""
    G = sorted(set(groups))
    gi = np.array([G.index(g) for g in groups])
    Z = np.zeros((len(y), len(G)))
    Z[np.arange(len(y)), gi] = 1.0
    A = np.hstack([Z, X])
    w = np.zeros(A.shape[1])
    pen = np.r_[np.zeros(len(G)), np.full(X.shape[1], lam)]
    for _ in range(iters):
        eta = A @ w
        p = 1 / (1 + np.exp(-eta))
        g = A.T @ (p - y) + pen * w
        H = (A * (p * (1 - p))[:, None]).T @ A + np.diag(pen) + 1e-9 * np.eye(A.shape[1])
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    icpt = {g: float(w[i]) for i, g in enumerate(G)}
    n = {g: int((gi == i).sum()) for i, g in enumerate(G)}
    mean_icpt = sum(icpt[g] * n[g] for g in G) / sum(n.values())
    return {"intercepts": icpt, "n": n, "mean_intercept": mean_icpt, "coef": w[len(G):]}


def predict(model, X, intercept=None):
    b0 = model["mean_intercept"] if intercept is None else intercept
    return 1 / (1 + np.exp(-(b0 + X @ model["coef"])))


def recalibrate(lp, y, iters=50):
    """Intercept and slope on the linear predictor: the tool's recalibration to a program's own rates."""
    A = np.c_[np.ones_like(lp), lp]
    w = np.array([0.0, 1.0])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(A @ w)))
        g = A.T @ (p - y)
        H = (A * (p * (1 - p))[:, None]).T @ A + 1e-9 * np.eye(2)
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return w


# a small gradient-boosted tree model, as a check on the logistic model (proposal E)
def fit_gbm(X, y, rounds=120, depth=3, lr=0.1, min_leaf=200, bins=24):
    edges = [np.unique(np.quantile(X[:, j], np.linspace(0, 1, bins + 1)[1:-1])) for j in range(X.shape[1])]
    B = np.column_stack([np.searchsorted(edges[j], X[:, j], side="right") for j in range(X.shape[1])])
    base = math.log(y.mean() / (1 - y.mean()))
    F = np.full(len(y), base)
    trees = []
    for _ in range(rounds):
        p = 1 / (1 + np.exp(-F))
        g, h = p - y, p * (1 - p)
        tree = grow(B, g, h, np.arange(len(y)), depth, min_leaf)
        F += lr * apply_tree(tree, B)
        trees.append(tree)
    return {"edges": edges, "base": base, "trees": trees, "lr": lr}


def grow(B, g, h, idx, depth, min_leaf, lam=1.0):
    G, H = g[idx].sum(), h[idx].sum()
    leaf = {"leaf": -G / (H + lam)}
    if depth == 0 or len(idx) < 2 * min_leaf:
        return leaf
    best = (0.0, None, None)
    for j in range(B.shape[1]):
        nb = B[:, j].max() + 1
        gs = np.bincount(B[idx, j], weights=g[idx], minlength=nb)
        hs = np.bincount(B[idx, j], weights=h[idx], minlength=nb)
        cnt = np.bincount(B[idx, j], minlength=nb)
        gl, hl, cl = np.cumsum(gs)[:-1], np.cumsum(hs)[:-1], np.cumsum(cnt)[:-1]
        gr, hr, cr = G - gl, H - hl, len(idx) - cl
        ok = (cl >= min_leaf) & (cr >= min_leaf)
        if not ok.any():
            continue
        gain = np.where(ok, gl ** 2 / (hl + lam) + gr ** 2 / (hr + lam) - G ** 2 / (H + lam), -np.inf)
        k = int(np.argmax(gain))
        if gain[k] > best[0]:
            best = (gain[k], j, k)
    if best[1] is None:
        return leaf
    j, k = best[1], best[2]
    left = idx[B[idx, j] <= k]
    right = idx[B[idx, j] > k]
    return {"f": j, "t": k, "l": grow(B, g, h, left, depth - 1, min_leaf), "r": grow(B, g, h, right, depth - 1, min_leaf)}


def apply_tree(t, B):
    out = np.empty(B.shape[0])
    stack = [(t, np.arange(B.shape[0]))]
    while stack:
        node, idx = stack.pop()
        if "leaf" in node:
            out[idx] = node["leaf"]
            continue
        m = B[idx, node["f"]] <= node["t"]
        stack.append((node["l"], idx[m]))
        stack.append((node["r"], idx[~m]))
    return out


def predict_gbm(m, X):
    B = np.column_stack([np.searchsorted(m["edges"][j], X[:, j], side="right") for j in range(X.shape[1])])
    F = np.full(X.shape[0], m["base"])
    for t in m["trees"]:
        F += m["lr"] * apply_tree(t, B)
    return 1 / (1 + np.exp(-F))


# ------------------------------------------------------------------ measures
def auc(y, s):
    y = np.asarray(y, bool)
    n1, n0 = y.sum(), (~y).sum()
    if n1 == 0 or n0 == 0:
        return None
    r = pd.Series(s).rank(method="average").values
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def wilson(k, n):
    if n < MIN_CELL:
        return None
    z, p = 1.96, k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {"rate": round(p, 4), "lo": round(max(0, c - h), 4), "hi": round(min(1, c + h), 4), "n": int(n)}


def tiers_of(score, rounds):
    """Within each round, the top 15% of scores are high, the next 35% medium, the rest low (D7, tied to workload)."""
    out = np.empty(len(score), dtype=object)
    df = pd.DataFrame({"s": score, "r": rounds})
    df["rank"] = df.groupby("r")["s"].rank(method="first", ascending=False)
    df["n"] = df.groupby("r")["s"].transform("size")
    q = df["rank"] / df["n"]
    out[:] = np.where(q <= TIERS[0], "high", np.where(q <= TIERS[0] + TIERS[1], "medium", "low"))
    return out


def evaluate(y, p, rounds, extra=None):
    y = np.asarray(y, float)
    res = {"n": int(len(y)), "events": int(y.sum()), "rate": round(float(y.mean()), 4), "auc": round(auc(y, p), 4) if auc(y, p) is not None else None,
           "brier": round(float(np.mean((p - y) ** 2)), 4), "brier_null": round(float(np.mean((y.mean() - y) ** 2)), 4)}
    dec = pd.qcut(pd.Series(p).rank(method="first"), 10, labels=False)
    cal = []
    for d in range(10):
        m = dec.values == d
        if m.sum() >= MIN_CELL:
            cal.append({"decile": d + 1, "predicted": round(float(p[m].mean()), 4), "observed": round(float(y[m].mean()), 4), "n": int(m.sum())})
    res["calibration"] = cal
    t = tiers_of(p, rounds)
    res["tiers"] = {k: wilson(int(y[t == k].sum()), int((t == k).sum())) for k in ("high", "medium", "low")}
    res["capture_high"] = round(float(y[t == "high"].sum() / y.sum()), 4) if y.sum() else None
    if extra:
        res.update(extra)
    return res


def overlap(a, b):
    return a and b and not (a["lo"] > b["hi"] or b["lo"] > a["hi"])


def decide_tiers(model_val):
    """Proposal E.5: each tier's realized rate on held-out data with its 95% interval; adjacent tiers whose intervals
    overlap are merged (fewer tiers rather than false precision). Every held-out table of the versions the tool offers
    before any refit is checked: other programs left out, and the program's own later rounds with the model as trained
    or recalibrated. The program-only refit ("own_rounds_only") is a separate version, which the tool backtests on the
    program's own data before offering it. Returns the tiers used and each overlap found."""
    found = []

    def walk(o, path):
        if isinstance(o, dict):
            t = o.get("tiers")
            if isinstance(t, dict) and {"high", "medium", "low"} <= set(t):
                for a, b in (("high", "medium"), ("medium", "low")):
                    if overlap(t[a], t[b]):
                        found.append({"table": path, "tiers": [a, b], "rates": [t[a]["rate"], t[b]["rate"]],
                                      "intervals": [[t[a]["lo"], t[a]["hi"]], [t[b]["lo"], t[b]["hi"]]]})
            for k, v in o.items():
                if k != "own_rounds_only":
                    walk(v, f"{path}/{k}" if path else k)
    walk(model_val, "")
    return (["high", "low"] if found else ["high", "medium", "low"]), found


# ------------------------------------------------------------------ main
def main():
    t0 = time.time()
    feats_d = [k for k, _, _ in DROP_FEATURES]
    feats_r = [k for k, _, _ in RET_FEATURES]
    D, R, META = [], [], {}
    for c in PROGRAMS:
        d, r, meta = build_pairs(c)
        D.append(d)
        if r is not None:
            R.append(r)
        META[c] = meta
        print(f"{LABEL[c]}: {len(d)} dropout pairs, loss rate {d['y'].mean():.3f}" + (f"; {len(r)} return pairs, return rate {r['y'].mean():.3f}" if r is not None else ""))
    D = pd.concat(D, ignore_index=True)
    R = pd.concat(R, ignore_index=True)
    D["y"] = D["y"].astype(float)
    R["y"] = R["y"].astype(float)
    val = {"meta": META, "dropout": {}, "return": {}}

    # ---- dropout: leave one program out, against the baselines and a boosted-tree check
    lopo, pooled_y, pooled_p, pooled_r = {}, [], [], []
    for c in PROGRAMS:
        tr, te = D[D["program"] != c], D[D["program"] == c]
        st = standardise(tr, feats_d)
        m = fit_logit(design(tr, feats_d, st), tr["y"].values, tr["program"].values)
        Xte = design(te, feats_d, st)
        p = predict(m, Xte)
        # baselines: the loss rate by rounds since joining (the handbook's hazard curve) and the dials rule
        bins = pd.cut(tr["k"], [0, 1, 2, 3, 6, 12, 10 ** 6], labels=False)
        rate = tr.groupby(bins)["y"].mean()
        p_haz = pd.cut(te["k"], [0, 1, 2, 3, 6, 12, 10 ** 6], labels=False).map(rate).fillna(tr["y"].mean()).values
        q75 = te.groupby("round")["k_complete"].transform(lambda s: s.quantile(0.75))
        rule = (te["k_complete"] > q75).astype(float).values
        gb = fit_gbm(design(tr, feats_d, st), tr["y"].values)
        p_gbm = predict_gbm(gb, Xte)
        ev = evaluate(te["y"].values, p, te["round"].values)
        ev["baseline_tenure"] = {"auc": round(auc(te["y"].values, p_haz), 4), "brier": round(float(np.mean((p_haz - te["y"].values) ** 2)), 4),
                                 "capture_high": round(float(te["y"].values[tiers_of(p_haz + 1e-9 * rng.random(len(p_haz)), te["round"].values) == "high"].sum() / te["y"].sum()), 4)}
        ev["baseline_dials_rule"] = {"auc": round(auc(te["y"].values, rule), 4), "flagged_share": round(float(rule.mean()), 4),
                                     "capture": round(float(te["y"].values[rule == 1].sum() / te["y"].sum()), 4)}
        ev["gbm_check"] = {"auc": round(auc(te["y"].values, p_gbm), 4), "brier": round(float(np.mean((p_gbm - te["y"].values) ** 2)), 4)}
        lopo[c] = ev
        pooled_y.append(te["y"].values); pooled_p.append(p); pooled_r.append(te["program"].values + ":" + te["round"].astype(str).values)
        print(f"  LOPO {LABEL[c]}: AUC {ev['auc']} (tenure {ev['baseline_tenure']['auc']}, dials rule {ev['baseline_dials_rule']['auc']}, trees {ev['gbm_check']['auc']}); "
              f"Brier {ev['brier']} vs null {ev['brier_null']}; high tier holds {ev['capture_high']} of losses")
    val["dropout"]["leave_one_program_out"] = lopo
    val["dropout"]["leave_one_program_out_pooled"] = evaluate(np.concatenate(pooled_y), np.concatenate(pooled_p), np.concatenate(pooled_r))

    # ---- dropout: rolling origin within each program, and the tool's path (pooled model recalibrated on the program's own past rounds)
    roll = {}
    for c in PROGRAMS:
        dc = D[D["program"] == c]
        others = D[D["program"] != c]
        st_o = standardise(others, feats_d)
        m_o = fit_logit(design(others, feats_d, st_o), others["y"].values, others["program"].values)
        outcome_rounds = sorted((dc["round"] + 1).unique())
        ys, ps_own, ps_recal, ps_pool, rs = [], [], [], [], []
        for r in outcome_rounds:
            past = dc[(dc["round"] + 1) < r]            # outcomes already seen when round r starts
            if past["round"].nunique() < 2 or past["y"].sum() < 20:
                continue
            te = dc[(dc["round"] + 1) == r]
            st = standardise(past, feats_d)
            m = fit_logit(design(past, feats_d, st), past["y"].values, np.array([c] * len(past)))
            p_own = predict(m, design(te, feats_d, st), m["intercepts"][c])
            lp_past = m_o["mean_intercept"] + design(past, feats_d, st_o) @ m_o["coef"]
            a, bslope = recalibrate(lp_past, past["y"].values)
            lp_te = m_o["mean_intercept"] + design(te, feats_d, st_o) @ m_o["coef"]
            ys.append(te["y"].values); ps_own.append(p_own); ps_recal.append(1 / (1 + np.exp(-(a + bslope * lp_te)))); ps_pool.append(1 / (1 + np.exp(-lp_te))); rs.append(te["round"].values)
        if not ys:
            continue
        y_, r_ = np.concatenate(ys), np.concatenate(rs)
        roll[c] = {"steps": len(ys), "own_rounds_only": evaluate(y_, np.concatenate(ps_own), r_), "pooled_recalibrated": evaluate(y_, np.concatenate(ps_recal), r_),
                   "pooled_as_is": evaluate(y_, np.concatenate(ps_pool), r_)}
        print(f"  rolling {LABEL[c]} ({len(ys)} rounds): own-data AUC {roll[c]['own_rounds_only']['auc']}, pooled+recalibrated AUC {roll[c]['pooled_recalibrated']['auc']} "
              f"(Brier {roll[c]['pooled_recalibrated']['brier']} vs pooled as is {roll[c]['pooled_as_is']['brier']})")
    val["dropout"]["rolling_origin"] = roll

    # ---- return: train on one of PHL and IND, test on the other; rolling origin within each
    lopo_r = {}
    for c in RETURN_PROGRAMS:
        tr, te = R[R["program"] != c], R[R["program"] == c]
        st = standardise(tr, feats_r)
        m = fit_logit(design(tr, feats_r, st), tr["y"].values, tr["program"].values)
        p = predict(m, design(te, feats_r, st))
        bins = pd.cut(tr["k"], [0, 1, 2, 3, 6, 12, 10 ** 6], labels=False)
        rate = tr.groupby(bins)["y"].mean()
        p_haz = pd.cut(te["k"], [0, 1, 2, 3, 6, 12, 10 ** 6], labels=False).map(rate).fillna(tr["y"].mean()).values
        ev = evaluate(te["y"].values, p, te["round"].values)
        ev["baseline_tenure"] = {"auc": round(auc(te["y"].values, p_haz), 4), "brier": round(float(np.mean((p_haz - te["y"].values) ** 2)), 4)}
        lopo_r[c] = ev
        print(f"  return, trained without {LABEL[c]}: AUC {ev['auc']} (tenure {ev['baseline_tenure']['auc']}); Brier {ev['brier']} vs null {ev['brier_null']}")
    val["return"]["other_program"] = lopo_r
    ys, ps, rs = [], [], []
    for c in RETURN_PROGRAMS:
        tr, te = R[R["program"] != c], R[R["program"] == c]
        st = standardise(tr, feats_r)
        m = fit_logit(design(tr, feats_r, st), tr["y"].values, tr["program"].values)
        ys.append(te["y"].values); ps.append(predict(m, design(te, feats_r, st))); rs.append(te["program"].values + ":" + te["round"].astype(str).values)
    val["return"]["other_program_pooled"] = evaluate(np.concatenate(ys), np.concatenate(ps), np.concatenate(rs))
    roll_r = {}
    for c in RETURN_PROGRAMS:
        rc, other = R[R["program"] == c], R[R["program"] != c]
        st_o = standardise(other, feats_r)
        m_o = fit_logit(design(other, feats_r, st_o), other["y"].values, other["program"].values)
        ys, ps_own, ps_recal, rs = [], [], [], []
        for r in sorted((rc["round"] + 4).unique()):              # outcomes are known three rounds after the miss
            past = rc[(rc["round"] + 4) < r]
            te = rc[(rc["round"] + 4) == r]
            if past["round"].nunique() < 2 or past["y"].sum() < 20 or (1 - past["y"]).sum() < 20 or not len(te):
                continue
            st = standardise(past, feats_r)
            m = fit_logit(design(past, feats_r, st), past["y"].values, np.array([c] * len(past)))
            ps_own.append(predict(m, design(te, feats_r, st), m["intercepts"][c]))
            a, bs = recalibrate(m_o["mean_intercept"] + design(past, feats_r, st_o) @ m_o["coef"], past["y"].values)
            ps_recal.append(1 / (1 + np.exp(-(a + bs * (m_o["mean_intercept"] + design(te, feats_r, st_o) @ m_o["coef"])))))
            ys.append(te["y"].values); rs.append(te["round"].values)
        if ys:
            y_, r_ = np.concatenate(ys), np.concatenate(rs)
            roll_r[c] = {"steps": len(ys), "own_rounds_only": evaluate(y_, np.concatenate(ps_own), r_), "other_recalibrated": evaluate(y_, np.concatenate(ps_recal), r_)}
            print(f"  return rolling {LABEL[c]} ({len(ys)} rounds): own-data AUC {roll_r[c]['own_rounds_only']['auc']} Brier {roll_r[c]['own_rounds_only']['brier']}; "
                  f"other program recalibrated AUC {roll_r[c]['other_recalibrated']['auc']} Brier {roll_r[c]['other_recalibrated']['brier']} (null {roll_r[c]['other_recalibrated']['brier_null']})")
    val["return"]["rolling_origin"] = roll_r

    # ---- the models the tool bundles: all six programs (dropout), PHL and IND (return)
    st_d = standardise(D, feats_d)
    m_d = fit_logit(design(D, feats_d, st_d), D["y"].values, D["program"].values)
    st_r = standardise(R, feats_r)
    m_r = fit_logit(design(R, feats_r, st_r), R["y"].values, R["program"].values)
    # tiers: if two adjacent tiers' held-out intervals overlap anywhere, merge them (fewer tiers rather than false precision)
    tiers_d, why_d = decide_tiers(val["dropout"])
    tiers_r, why_r = decide_tiers(val["return"])
    out = {
        "schema": "rtm-riskmodels-1.0", "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "trained_on": {LABEL[c]: META[c] for c in PROGRAMS},
        "lambda": LAMBDA, "tiers": {"high": TIERS[0], "medium": TIERS[1], "dropout": tiers_d, "return": tiers_r,
                                    "overlaps": {"dropout": why_d, "return": why_r}}, "tool_codes": TOOL_CODES,
        "tenure_bins": [[lo, hi, name] for lo, hi, name in TENURE_BINS], "tenure_reference": TENURE_REF,
        "dropout": {"features": [{"key": k, "label": l, "group": g, "mean": st_d[k][0], "sd": st_d[k][1], "coef": float(b)} for (k, l, g), b in zip(DROP_FEATURES, m_d["coef"])],
                    "mean_intercept": m_d["mean_intercept"], "intercepts": {LABEL[k]: v for k, v in m_d["intercepts"].items()}, "n": {LABEL[k]: v for k, v in m_d["n"].items()},
                    "loss_rate": round(float(D["y"].mean()), 4), "groups": [{"key": k, "label": l, "features": f} for k, l, f in DROP_GROUPS]},
        "return": {"features": [{"key": k, "label": l, "group": g, "mean": st_r[k][0], "sd": st_r[k][1], "coef": float(b)} for (k, l, g), b in zip(RET_FEATURES, m_r["coef"])],
                   "mean_intercept": m_r["mean_intercept"], "intercepts": {LABEL[k]: v for k, v in m_r["intercepts"].items()}, "n": {LABEL[k]: v for k, v in m_r["n"].items()},
                   "return_rate": round(float(R["y"].mean()), 4), "groups": [{"key": k, "label": l, "features": f} for k, l, f in RET_GROUPS]},
        "codes": {LABEL[c]: {k: (sorted(v) if v is not None else None) for k, v in CODES[c].items()} for c in PROGRAMS},
    }
    out["validation_summary"] = {
        "dropout_leave_one_program_out": {LABEL[c]: {k: lopo[c][k] for k in ("n", "events", "rate", "auc", "brier", "brier_null", "capture_high", "tiers")} | {
            "auc_tenure_only": lopo[c]["baseline_tenure"]["auc"], "auc_dials_rule": lopo[c]["baseline_dials_rule"]["auc"], "auc_trees": lopo[c]["gbm_check"]["auc"],
            "capture_tenure_only": lopo[c]["baseline_tenure"]["capture_high"]} for c in PROGRAMS},
        "dropout_rolling_origin": {LABEL[c]: {"steps": v["steps"], "auc_own": v["own_rounds_only"]["auc"], "auc_pooled_recalibrated": v["pooled_recalibrated"]["auc"],
                                              "brier_own": v["own_rounds_only"]["brier"], "brier_pooled_recalibrated": v["pooled_recalibrated"]["brier"], "brier_pooled_as_is": v["pooled_as_is"]["brier"],
                                              "capture_high_recalibrated": v["pooled_recalibrated"]["capture_high"]} for c, v in roll.items()},
        "return_other_program": {LABEL[c]: {k: lopo_r[c][k] for k in ("n", "events", "rate", "auc", "brier", "brier_null", "tiers")} | {"auc_tenure_only": lopo_r[c]["baseline_tenure"]["auc"]} for c in RETURN_PROGRAMS},
        "return_rolling_origin": {LABEL[c]: {"steps": v["steps"], "auc_own": v["own_rounds_only"]["auc"], "brier_own": v["own_rounds_only"]["brier"],
                                             "auc_other_recalibrated": v["other_recalibrated"]["auc"], "brier_other_recalibrated": v["other_recalibrated"]["brier"],
                                             "brier_null": v["other_recalibrated"]["brier_null"]} for c, v in roll_r.items()},
    }
    json.dump(out, open(os.path.join(HERE, "risk_models.json"), "w"), indent=1)
    json.dump(val, open(os.path.join(HERE, "validation.json"), "w"), indent=1, default=float)
    print(f"written models/risk_models.json and models/validation.json in {time.time() - t0:.0f} s; tiers used: dropout {tiers_d}, return {tiers_r}")


def tiers_only():
    """Apply the tier rule to the stored backtests (models/validation.json) and refresh the labels in risk_models.json; reads no data."""
    val = json.load(open(os.path.join(HERE, "validation.json")))
    out = json.load(open(os.path.join(HERE, "risk_models.json")))
    (td, wd), (tr, wr) = decide_tiers(val["dropout"]), decide_tiers(val["return"])
    out["tiers"].update({"dropout": td, "return": tr, "overlaps": {"dropout": wd, "return": wr}})
    # the labels are wording, not fitted values: take them from this script
    for kind, feats, groups in (("dropout", DROP_FEATURES, DROP_GROUPS), ("return", RET_FEATURES, RET_GROUPS)):
        lab = {k: l for k, l, _ in feats}
        for f in out[kind]["features"]:
            f["label"] = lab[f["key"]]
        glab = {k: l for k, l, _ in groups}
        for g in out[kind]["groups"]:
            g["label"] = glab[g["key"]]
    json.dump(out, open(os.path.join(HERE, "risk_models.json"), "w"), indent=1)
    print(f"tiers used: dropout {td} ({len(wd)} overlaps), return {tr} ({len(wr)} overlaps: {[(w['table'], w['tiers']) for w in wr]})")


if __name__ == "__main__":
    sys.exit(tiers_only() if "--tiers-only" in sys.argv else main())
