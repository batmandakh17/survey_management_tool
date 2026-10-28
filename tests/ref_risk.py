"""The training script's own feature, scoring and refitting code, run on the tool's merged history, to check the browser.

Builds case and dial tables shaped like the handbook's (with tests/ref_stats.py, which follows 10_build_attempts.py) from the
leader's merged calls files, then calls models/train_risk.py's feature code with the tool's result codes.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "models"))
import ref_stats  # noqa: E402
import train_risk as TR  # noqa: E402

MODEL = json.load(open(os.path.join(HERE, "..", "models", "risk_models.json")))


def tables(paths):
    kept, cases, _ = ref_stats.build(ref_stats.read_calls(paths))
    di = pd.DataFrame([{"hhid": x["hhid"], "round": x["round"], "ts": pd.Timestamp(x["ts"]), "status_raw": x["status"], "dur_min": x["dur"],
                        "operator": x["op"], "attempt": x["attempt"], "k_complete": cases[(x["hhid"], x["round"])]["k"]} for x in kept])
    di["k_complete"] = di["k_complete"].astype(float)
    ca = pd.DataFrame([{"hhid": c["hhid"], "round": c["round"], "n_att": c["n_att"], "n_days": c["n_days"], "k_complete": float(c["k"]) if c["k"] else np.nan,
                        "completed": c["k"] is not None, "day_complete": float(c["dials"][c["k"] - 1]["day_idx"]) if c["k"] else np.nan} for c in cases.values()])
    return ca, di


def features(paths):
    ca, di = tables(paths)
    codes = {k: set(v) for k, v in MODEL["tool_codes"].items()}
    D, R, _ = TR.pairs_from_tables(ca, di, codes, "TOOL", True, require_outcome=False)
    return D, R


def lp(spec, row):
    total = spec["mean_intercept"]
    for f in spec["features"]:
        v = row.get(f["key"])
        z = 0.0 if v is None or (isinstance(v, float) and np.isnan(v)) else (float(v) - f["mean"]) / f["sd"]
        total += z * f["coef"]
    return total


def rows_of(df, keys):
    out = {}
    for _, r in df.iterrows():
        out[f"{r['hhid']}|{int(r['round'])}"] = {k: (None if pd.isna(r[k]) else float(r[k])) for k in keys} | {"_y": None if pd.isna(r["y"]) else float(r["y"])}
    return out


def recalibration(spec, rows):
    """Intercept and slope on the five-program model's linear predictor, with the training script's own function."""
    keys = [k for k, v in rows.items() if v["_y"] is not None]
    x = np.array([lp(spec, rows[k]) for k in keys])
    y = np.array([rows[k]["_y"] for k in keys])
    a, b = TR.recalibrate(x, y)
    return float(a), float(b), len(keys)


def refit(spec, rows):
    keys = [k for k, v in rows.items() if v["_y"] is not None]
    feats = [f["key"] for f in spec["features"]]
    df = pd.DataFrame([{k: (np.nan if rows[h][k] is None else rows[h][k]) for k in feats} | {"y": rows[h]["_y"]} for h in keys])
    st = TR.standardise(df, feats)
    m = TR.fit_logit(TR.design(df, feats, st), df["y"].values, np.array(["own"] * len(df)))
    return m["intercepts"]["own"], [float(c) for c in m["coef"]]
