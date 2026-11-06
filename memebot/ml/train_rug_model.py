"""Train/evaluate a high-risk memecoin detector on MELT with a TIME-BASED split.

Features are pre-migration only; label = outcome after migration (high/medium/low risk).
Usage: python -m memebot.ml.train_rug_model --pkl feature.pkl --labels label.csv
"""
import argparse

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score

from .melt_data import load_dataset

DROP = {"mint_address", "mint_ts", "label", "min_ratio", "manipulated", "return_ratio"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pkl", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--test-frac", type=float, default=0.3)
    a = ap.parse_args()

    df = load_dataset(a.pkl, a.labels).sort_values("mint_ts").reset_index(drop=True)
    X_cols = [c for c in df.columns if c not in DROP]
    y = (df["label"] == "high").astype(int)
    cut = int(len(df) * (1 - a.test_frac))
    tr, te = df.iloc[:cut], df.iloc[cut:]
    print(f"rows={len(df)} features={len(X_cols)} train={len(tr)} test={len(te)} "
          f"(time split; test starts {pd.to_datetime(te.mint_ts.min(), unit='s')})")
    print(f"high-risk base rate  train={y[:cut].mean():.3f}  test={y[cut:].mean():.3f}")

    m = lgb.LGBMClassifier(n_estimators=400, learning_rate=0.03, num_leaves=31,
                           subsample=0.8, colsample_bytree=0.8, subsample_freq=1,
                           min_child_samples=40, random_state=42, verbose=-1)
    m.fit(tr[X_cols], y[:cut])
    p = m.predict_proba(te[X_cols])[:, 1]
    yt = y[cut:].values
    print(f"\nAUROC={roc_auc_score(yt, p):.3f}  AUPRC={average_precision_score(yt, p):.3f} "
          f"(AUPRC of a coin flip = base rate {yt.mean():.3f})")

    print("\nthr   precision recall  | tokens kept  mean_ret  median_ret  P(ret>0)  P(ret>+50%)")
    r = te["return_ratio"].values
    print(f"all   {'-':>9} {'-':>6}  | {len(te):>11} {r.mean():9.2f} {np.median(r):11.2f} {(r>0).mean():9.3f} {(r>0.5).mean():11.3f}   (no filter)")
    for thr in (0.5, 0.7, 0.8, 0.9, 0.95):
        pred = p >= thr
        pr, rc, _, _ = precision_recall_fscore_support(yt, pred, average="binary", zero_division=0)
        keep = ~pred
        k = r[keep]
        if len(k) == 0:
            continue
        print(f"{thr:<5} {pr:9.3f} {rc:6.3f}  | {keep.sum():>11} {k.mean():9.2f} {np.median(k):11.2f} {(k>0).mean():9.3f} {(k>0.5).mean():11.3f}")

    imp = pd.Series(m.booster_.feature_importance("gain"), index=X_cols).sort_values(ascending=False)
    print("\nTop 15 features by gain:")
    for k_, v in (imp / imp.sum()).head(15).items():
        print(f"  {v:6.3f}  {k_}")


if __name__ == "__main__":
    main()
