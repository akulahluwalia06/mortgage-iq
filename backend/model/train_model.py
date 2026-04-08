"""
Canadian Mortgage ML Model Training Script
==========================================
Uses real data when available (data/loan_data.csv), otherwise falls back to
20 000-sample synthetic data calibrated to Canadian mortgage market statistics.

Real dataset: Kaggle "Realistic Loan Approval Dataset (US & Canada)"
  kaggle datasets download -d parthpatel2130/realistic-loan-approval-dataset-us-and-canada
  unzip *.zip -d backend/model/data/

Canadian calibration sources:
  - CMHC 2023 mortgage statistics
  - Statistics Canada income tables
  - Bank of Canada rate data 2018-2024
  - OSFI B-20 stress-test rules
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error
import joblib
import os
import sys

np.random.seed(42)

# ── Constants ─────────────────────────────────────────────────────────────────
FEATURES = [
    "annual_income", "credit_score", "down_payment_pct", "property_value",
    "existing_monthly_debt", "gds_ratio", "tds_ratio",
    "employment_type", "province", "amortization", "property_type",
]

PROVINCE_MAP = {
    "ON": 0, "BC": 1, "AB": 2, "QC": 3, "MB": 4,
    "SK": 5, "NS": 6, "NB": 7, "NL": 8, "PE": 9,
}
PROVINCE_MEDIAN_PRICE = {
    0: 850000, 1: 950000, 2: 450000, 3: 420000, 4: 340000,
    5: 315000, 6: 375000, 7: 265000, 8: 280000, 9: 295000,
}
GDS_LIMIT = 0.39
TDS_LIMIT = 0.44
STRESS_TEST_FLOOR = 5.25


# ── Real-data loader ─────────────────────────────────────────────────────────
def load_kaggle_dataset(path: str) -> pd.DataFrame | None:
    """
    Load and map the Kaggle 'Realistic Loan Approval Dataset (US & Canada)'
    to our internal feature schema.

    Expected CSV columns (subset used):
        annual_income, credit_score, loan_amount, property_value,
        down_payment, loan_status (Approved/Rejected), interest_rate,
        loan_term (months), employment_type, debt_to_income_ratio
    """
    if not os.path.exists(path):
        return None

    print(f"Loading real dataset from {path} …")
    raw = pd.read_csv(path)
    print(f"  Raw shape: {raw.shape}")
    print(f"  Columns: {list(raw.columns)}")

    # Normalise column names
    raw.columns = raw.columns.str.strip().str.lower().str.replace(" ", "_")

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

            # ── Property / loan amounts ──────────────────────────────────────
            # This dataset has loan_amount but not property_value or down_payment.
            # Derive property value from loan using loan_to_income_ratio or DTI proxy.
            loan = float(r.get("loan_amount", r.get("loan_size", 0)))
            pv = float(r.get("property_value", r.get("property_price", 0)))

            if pv <= 0 and loan > 0:
                # Assume median down payment of 10% → property_value = loan / 0.90
                pv = loan / 0.90
            if pv <= 0 or loan <= 0:
                continue

            dp = pv - loan
            dp_pct = dp / pv
            if dp_pct <= 0 or dp_pct >= 1:
                dp_pct = 0.10
                dp = pv * dp_pct

            # ── Existing debt ────────────────────────────────────────────────
            # current_debt is total outstanding debt balance, not monthly payments
            current_debt = float(r.get("current_debt", 0))
            dti = float(r.get("debt_to_income_ratio", 0))
            if dti > 0:
                # DTI = monthly debt payments / monthly income → monthly payments
                monthly_debt = dti * income / 12
            elif current_debt > 0:
                monthly_debt = current_debt * 0.02  # assume ~2% of balance as monthly payment
            else:
                monthly_debt = 0.0

            # ── GDS / TDS ────────────────────────────────────────────────────
            monthly_income = income / 12
            r_monthly = STRESS_TEST_FLOOR / 100 / 12
            n_payments = 300  # 25yr default
            est_payment = loan * r_monthly * (1 + r_monthly) ** n_payments / \
                          ((1 + r_monthly) ** n_payments - 1)
            prop_tax_heat = pv * 0.015 / 12
            gds = (est_payment + prop_tax_heat) / monthly_income
            tds = gds + monthly_debt / monthly_income

            # ── Employment ───────────────────────────────────────────────────
            emp_raw = str(r.get("occupation_status", r.get("employment_type",
                          r.get("employment_status", "employed")))).lower()
            if "self" in emp_raw:
                emp = 1
            elif "contract" in emp_raw or "part" in emp_raw or "freelan" in emp_raw or "unempl" in emp_raw:
                emp = 2
            else:
                emp = 0  # employed / salaried

            # ── Province (random — dataset doesn't have Canadian province) ───
            province_enc = int(np.random.randint(0, 10))

            # ── Amortization ─────────────────────────────────────────────────
            term_months = float(r.get("loan_term", r.get("term_months", 300)))
            amort_years = round(term_months / 12)
            if amort_years <= 15:
                amort = 15
            elif amort_years <= 20:
                amort = 20
            elif amort_years <= 25:
                amort = 25
            else:
                amort = 30

            # ── Property type ────────────────────────────────────────────────
            pt_raw = str(r.get("property_type", r.get("home_type", r.get("product_type", "house")))).lower()
            if "condo" in pt_raw or "apartment" in pt_raw:
                pt = 0
            elif "town" in pt_raw or "semi" in pt_raw:
                pt = 2
            else:
                pt = 1

            # ── Approval ─────────────────────────────────────────────────────
            # loan_status: 1 = approved, 0 = rejected
            status_raw = r.get("loan_status", r.get("approval_status", "1"))
            if isinstance(status_raw, (int, float)):
                approved = int(status_raw)
            else:
                s = str(status_raw).lower()
                approved = 1 if ("approv" in s or s == "1") else 0

            # ── Interest rate ─────────────────────────────────────────────────
            rate = float(r.get("interest_rate", r.get("loan_rate", 0)))
            # Dataset rates are in US context (~5-20%); clamp to Canadian range
            if rate <= 0 or rate > 15:
                rate = (5.5
                        - (cs - 650) * 0.005
                        + (1 - dp_pct) * 1.2
                        + (emp == 1) * 0.35
                        + (emp == 2) * 0.20
                        + np.random.normal(0, 0.15))
            rate = float(np.clip(rate, 2.5, 9.5))

            rows.append({
                "annual_income": income,
                "credit_score": cs,
                "down_payment_pct": dp_pct,
                "property_value": pv,
                "existing_monthly_debt": monthly_debt,
                "gds_ratio": gds,
                "tds_ratio": tds,
                "employment_type": emp,
                "province": province_enc,
                "amortization": amort,
                "property_type": pt,
                "approved": approved,
                "interest_rate": rate,
            })
        except (ValueError, TypeError, KeyError):
            continue

    if not rows:
        print("  ⚠️  No usable rows extracted from real dataset — falling back to synthetic.")
        return None

    df = pd.DataFrame(rows)
    # Scale property values to Canadian market (dataset may use USD)
    cad_usd = 1.36
    if df["property_value"].median() < 300_000:
        df["property_value"] *= cad_usd
        df["annual_income"] *= cad_usd
        df["existing_monthly_debt"] *= cad_usd
    print(f"  Extracted {len(df)} usable rows from real dataset.")
    return df


# ── Synthetic data generator ─────────────────────────────────────────────────
def generate_synthetic(n: int = 20_000) -> pd.DataFrame:
    print(f"Generating {n} synthetic samples calibrated to Canadian market …")
    province = np.random.choice(list(PROVINCE_MEDIAN_PRICE.keys()), n)
    employment_type = np.random.choice([0, 1, 2], n, p=[0.65, 0.20, 0.15])
    property_type = np.random.choice([0, 1, 2], n, p=[0.30, 0.55, 0.15])
    amortization = np.random.choice([15, 20, 25, 30], n, p=[0.10, 0.20, 0.55, 0.15])

    annual_income = np.random.lognormal(mean=11.3, sigma=0.45, size=n).clip(35000, 500000)
    credit_score = np.random.normal(loc=680, scale=80, size=n).clip(300, 900).astype(int)

    base_price = np.array([PROVINCE_MEDIAN_PRICE[p] for p in province])
    property_value = (base_price * np.random.lognormal(0, 0.35, n)).clip(150000, 3_000_000)

    min_dp = np.where(
        property_value < 500_000, 0.05,
        np.where(property_value < 1_000_000, 0.10, 0.20),
    )
    down_payment_pct = (min_dp + np.random.exponential(scale=0.08, size=n)).clip(min_dp, 0.80)
    existing_monthly_debt = np.random.exponential(scale=400, size=n).clip(0, 4000)

    monthly_income = annual_income / 12
    est_payment = (property_value - down_payment_pct * property_value) * 0.005
    prop_tax_heat = property_value * 0.015 / 12
    gds_ratio = (est_payment + prop_tax_heat) / monthly_income
    tds_ratio = gds_ratio + existing_monthly_debt / monthly_income

    approved = (
        (credit_score >= 600)
        & (gds_ratio <= GDS_LIMIT)
        & (tds_ratio <= TDS_LIMIT)
        & (down_payment_pct >= min_dp)
        & (annual_income >= 40_000)
        & ~((employment_type == 1) & (credit_score < 650))
    ).astype(int)
    approved ^= (np.random.random(n) < 0.05).astype(int)  # 5% noise

    rate = (
        5.5
        - (credit_score - 650) * 0.005
        + (1 - down_payment_pct) * 1.2
        + (employment_type == 1) * 0.35
        + (employment_type == 2) * 0.20
        + np.random.normal(0, 0.2, n)
    ).clip(2.5, 9.5)

    return pd.DataFrame({
        "annual_income": annual_income,
        "credit_score": credit_score,
        "down_payment_pct": down_payment_pct,
        "property_value": property_value,
        "existing_monthly_debt": existing_monthly_debt,
        "gds_ratio": gds_ratio,
        "tds_ratio": tds_ratio,
        "employment_type": employment_type,
        "province": province,
        "amortization": amortization,
        "property_type": property_type,
        "approved": approved,
        "interest_rate": rate,
    })


# ── Main ──────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
KAGGLE_CSV = os.path.join(DATA_DIR, "loan_data.csv")

real_df = load_kaggle_dataset(KAGGLE_CSV)
synth_df = generate_synthetic(20_000)

if real_df is not None:
    # Blend: real data + synthetic (Canadian rules / CMHC calibration)
    df = pd.concat([real_df, synth_df], ignore_index=True)
    print(f"Combined dataset: {len(df)} rows ({len(real_df)} real + {len(synth_df)} synthetic)")
else:
    df = synth_df

print(f"\nDataset shape: {df.shape}")
print(f"Approval rate: {df['approved'].mean():.1%}")
print(f"Avg interest rate: {df['interest_rate'].mean():.2f}%")
print(df[FEATURES + ['approved', 'interest_rate']].describe().to_string())

# ── Train / test split ────────────────────────────────────────────────────────
X = df[FEATURES]
y_approval = df["approved"]
y_rate = df["interest_rate"]

X_train, X_test, ya_train, ya_test, yr_train, yr_test = train_test_split(
    X, y_approval, y_rate, test_size=0.20, random_state=42
)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

# ── Approval classifier ───────────────────────────────────────────────────────
clf = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
clf.fit(X_train_s, ya_train)
print(f"\nApproval model accuracy: {accuracy_score(ya_test, clf.predict(X_test_s)):.3f}")

# ── Interest rate regressor ───────────────────────────────────────────────────
reg = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, random_state=42)
reg.fit(X_train_s, yr_train)
print(f"Rate model MAE: {mean_absolute_error(yr_test, reg.predict(X_test_s)):.4f}%")

# ── Save artifacts ────────────────────────────────────────────────────────────
out_dir = os.path.dirname(__file__)
joblib.dump(clf,     os.path.join(out_dir, "approval_model.pkl"))
joblib.dump(reg,     os.path.join(out_dir, "rate_model.pkl"))
joblib.dump(scaler,  os.path.join(out_dir, "scaler.pkl"))
joblib.dump(FEATURES, os.path.join(out_dir, "features.pkl"))

print("\n✅ Models saved successfully.")
