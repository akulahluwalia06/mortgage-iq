"""
Canadian Mortgage ML Model — Training Script

Uses real data when available (data/loan_data.csv), then blends with
synthetic Canadian-calibrated data from constants.generate_synthetic().

Real dataset: Kaggle "Realistic Loan Approval Dataset (US & Canada)"
  kaggle datasets download -d parthpatel2130/realistic-loan-approval-dataset-us-and-canada
  unzip *.zip -d backend/model/data/
  mv backend/model/data/Loan_approval_data_2025.csv backend/model/data/loan_data.csv
"""

import os
import sys

# Allow running directly from the backend/model/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error
import joblib

from constants import (
    FEATURES, PROVINCE_MAP, PROVINCE_MEDIAN_PRICE,
    GDS_LIMIT, TDS_LIMIT, STRESS_TEST_FLOOR, RATE_MIN, RATE_MAX,
    CAD_USD_RATE, compute_gds_tds, generate_synthetic,
)


# ── Real-data loader ──────────────────────────────────────────────────────────
def load_kaggle_dataset(path: str) -> pd.DataFrame | None:
    """
    Load and map the Kaggle loan dataset to our internal feature schema.

    Handles the specific column layout of:
      Loan_approval_data_2025.csv (50 000 rows, 20 columns)
    """
    if not os.path.exists(path):
        return None

    print(f"Loading real dataset from {path} …")
    raw = pd.read_csv(path)
    print(f"  Raw shape: {raw.shape}")
    raw.columns = raw.columns.str.strip().str.lower().str.replace(" ", "_")

    rng  = np.random.default_rng(0)
    rows = []

    for _, r in raw.iterrows():
        try:
            # ── Income ───────────────────────────────────────────────────────
            income = float(r.get("annual_income", r.get("income", 0)))
            if income <= 0:
                continue

            # ── Credit score ─────────────────────────────────────────────────
            cs = float(r.get("credit_score", r.get("fico_score", 650)))
            cs = max(300, min(900, cs))

            # ── Loan / property values ────────────────────────────────────────
            loan = float(r.get("loan_amount", r.get("loan_size", 0)))
            pv   = float(r.get("property_value", r.get("property_price", 0)))

            if pv <= 0 and loan > 0:
                pv = loan / 0.90           # assume 10% down payment
            if pv <= 0 or loan <= 0:
                continue

            dp     = max(pv - loan, 0.0)
            dp_pct = dp / pv
            if not (0 < dp_pct < 1):
                dp_pct = 0.10
                dp     = pv * dp_pct

            # ── Existing monthly debt ─────────────────────────────────────────
            dti  = float(r.get("debt_to_income_ratio", 0))
            debt = (dti * income / 12) if dti > 0 else float(r.get("current_debt", 0)) * 0.02

            # ── GDS / TDS ─────────────────────────────────────────────────────
            amort    = 25
            term_raw = float(r.get("loan_term", r.get("term_months", 300)))
            if term_raw > 0:
                amort_yr = round(term_raw / 12)
                amort    = max(15, min(30, round(amort_yr / 5) * 5))
                if amort not in (15, 20, 25, 30):
                    amort = 25

            gds, tds = compute_gds_tds(pv - dp, pv, income, debt, amort)

            # ── Employment ────────────────────────────────────────────────────
            emp_raw = str(r.get("occupation_status", r.get("employment_type", "employed"))).lower()
            if "self" in emp_raw:
                emp = 1
            elif any(k in emp_raw for k in ("contract", "part", "freelan", "unempl")):
                emp = 2
            else:
                emp = 0

            # ── Province (random — dataset is not province-labelled) ──────────
            province_enc = int(rng.integers(0, 10))

            # ── Property type ─────────────────────────────────────────────────
            pt_raw = str(r.get("property_type", r.get("product_type", "house"))).lower()
            if "condo" in pt_raw or "apartment" in pt_raw:
                pt = 0
            elif "town" in pt_raw or "semi" in pt_raw:
                pt = 2
            else:
                pt = 1

            # ── Approval ──────────────────────────────────────────────────────
            status = r.get("loan_status", r.get("approval_status", 1))
            if isinstance(status, (int, float)):
                approved = int(status)
            else:
                approved = 1 if "approv" in str(status).lower() or str(status) == "1" else 0

            # ── Interest rate ─────────────────────────────────────────────────
            rate = float(r.get("interest_rate", r.get("loan_rate", 0)))
            if rate <= 0 or rate > 15:
                rate = (5.5
                        - (cs - 650) * 0.005
                        + (1 - dp_pct) * 1.2
                        + (emp == 1) * 0.35
                        + (emp == 2) * 0.20
                        + float(rng.normal(0, 0.15)))
            rate = float(np.clip(rate, RATE_MIN, RATE_MAX))

            rows.append({
                "annual_income":         income,
                "credit_score":          cs,
                "down_payment_pct":      dp_pct,
                "property_value":        pv,
                "existing_monthly_debt": debt,
                "gds_ratio":             gds,
                "tds_ratio":             tds,
                "employment_type":       emp,
                "province":              province_enc,
                "amortization":          amort,
                "property_type":         pt,
                "approved":              approved,
                "interest_rate":         rate,
            })
        except (ValueError, TypeError, KeyError, ZeroDivisionError):
            continue

    if not rows:
        print("  ⚠️  No usable rows extracted — falling back to synthetic only.")
        return None

    df = pd.DataFrame(rows)

    # Scale to CAD if values look like USD
    if df["property_value"].median() < 300_000:
        df["property_value"]        *= CAD_USD_RATE
        df["annual_income"]         *= CAD_USD_RATE
        df["existing_monthly_debt"] *= CAD_USD_RATE

    print(f"  Extracted {len(df):,} usable rows from real dataset.")
    return df


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    DATA_DIR   = os.path.join(os.path.dirname(__file__), "data")
    KAGGLE_CSV = os.path.join(DATA_DIR, "loan_data.csv")

    real_df   = load_kaggle_dataset(KAGGLE_CSV)
    synth_df  = generate_synthetic(n=20_000, seed=42)

    if real_df is not None:
        df = pd.concat([real_df, synth_df], ignore_index=True)
        print(f"Combined dataset: {len(df):,} rows ({len(real_df):,} real + {len(synth_df):,} synthetic)")
    else:
        df = synth_df
        print(f"Synthetic-only dataset: {len(df):,} rows")

    print(f"\nApproval rate: {df['approved'].mean():.1%}")
    print(f"Avg interest rate: {df['interest_rate'].mean():.2f}%")

    X  = df[FEATURES]
    ya = df["approved"]
    yr = df["interest_rate"]

    X_train, X_test, ya_train, ya_test, yr_train, yr_test = train_test_split(
        X, ya, yr, test_size=0.20, random_state=42
    )

    scaler     = StandardScaler()
    X_train_s  = scaler.fit_transform(X_train)
    X_test_s   = scaler.transform(X_test)

    clf = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
    clf.fit(X_train_s, ya_train)
    print(f"\nApproval model accuracy: {accuracy_score(ya_test, clf.predict(X_test_s)):.3f}")

    reg = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, random_state=42)
    reg.fit(X_train_s, yr_train)
    print(f"Rate model MAE: {mean_absolute_error(yr_test, reg.predict(X_test_s)):.4f}%")

    out = os.path.dirname(__file__)
    joblib.dump(clf,      os.path.join(out, "approval_model.pkl"))
    joblib.dump(reg,      os.path.join(out, "rate_model.pkl"))
    joblib.dump(scaler,   os.path.join(out, "scaler.pkl"))
    joblib.dump(FEATURES, os.path.join(out, "features.pkl"))

    print("\n✅ Models saved successfully.")
