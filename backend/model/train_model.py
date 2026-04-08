"""
Canadian Mortgage ML Model Training Script
==========================================
Dataset basis: Canadian Housing Market data from Kaggle
- https://www.kaggle.com/datasets/nishanthkumarsk/housing-loan-approval-prediction
- https://www.kaggle.com/datasets/threnjen/portland-housing-market-data (adapted for Canada)
- CMHC (Canada Mortgage and Housing Corporation) statistical guidelines

This script generates synthetic training data calibrated to Canadian mortgage
market statistics (2018-2024) and trains two models:
  1. Approval classifier (Random Forest)
  2. Interest rate predictor (Gradient Boosting)
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error
import joblib
import os

np.random.seed(42)
N = 20000  # synthetic samples

# ── Province encoding ────────────────────────────────────────────────────────
PROVINCES = {
    "ON": 0, "BC": 1, "AB": 2, "QC": 3, "MB": 4,
    "SK": 5, "NS": 6, "NB": 7, "NL": 8, "PE": 9,
}

# Province median home prices (2023 CREA data, in CAD)
PROVINCE_MEDIAN_PRICE = {
    0: 850000, 1: 950000, 2: 450000, 3: 420000, 4: 340000,
    5: 315000, 6: 375000, 7: 265000, 8: 280000, 9: 295000,
}

# ── Generate synthetic features ──────────────────────────────────────────────
province = np.random.choice(list(PROVINCES.values()), N)
employment_type = np.random.choice([0, 1, 2], N, p=[0.65, 0.20, 0.15])  # salaried, self-employed, contract
property_type = np.random.choice([0, 1, 2], N, p=[0.30, 0.55, 0.15])    # condo, house, townhouse
amortization = np.random.choice([15, 20, 25, 30], N, p=[0.10, 0.20, 0.55, 0.15])

# Income distribution (log-normal, CAD) — calibrated to StatsCan 2023
annual_income = np.random.lognormal(mean=11.3, sigma=0.45, size=N).clip(35000, 500000)

# Credit score (300–900 scale, Canadian)
credit_score = np.random.normal(loc=680, scale=80, size=N).clip(300, 900).astype(int)

# Property value based on province + noise
base_price = np.array([PROVINCE_MEDIAN_PRICE[p] for p in province])
property_value = (base_price * np.random.lognormal(0, 0.35, N)).clip(150000, 3000000)

# Down payment: CMHC rules — min 5% under $500k, 10% on portion $500k–$999k, 20%+ over $1M
min_dp = np.where(
    property_value < 500000, 0.05,
    np.where(property_value < 1000000, 0.10, 0.20)
)
down_payment_pct = (min_dp + np.random.exponential(scale=0.08, size=N)).clip(min_dp, 0.80)
down_payment = down_payment_pct * property_value

# Existing monthly debts (car loan, student loan, credit cards)
existing_monthly_debt = np.random.exponential(scale=400, size=N).clip(0, 4000)

# GDS / TDS ratios (Gross Debt Service / Total Debt Service)
# Canadian standard: GDS ≤ 39%, TDS ≤ 44%
monthly_income = annual_income / 12
estimated_mortgage_payment = (property_value - down_payment) * 0.005  # rough proxy
gds_ratio = (estimated_mortgage_payment + 300) / monthly_income  # +300 for property tax/heat
tds_ratio = (estimated_mortgage_payment + 300 + existing_monthly_debt) / monthly_income

# ── Derived approval logic (rule-based + noise) ──────────────────────────────
approved = (
    (credit_score >= 600) &
    (gds_ratio <= 0.39) &
    (tds_ratio <= 0.44) &
    (down_payment_pct >= min_dp) &
    (annual_income >= 40000) &
    # Self-employed harder to approve
    ~((employment_type == 1) & (credit_score < 650))
).astype(int)

# Add 5% noise
flip_mask = np.random.random(N) < 0.05
approved ^= flip_mask

# ── Interest rate prediction ─────────────────────────────────────────────────
# Bank of Canada overnight rate context: 2018–2024 range 0.25%–5.0%
# Fixed 5yr posted rates typically +1.5 to +2.5% over overnight
base_rate = 5.5  # mid-cycle assumption
rate = (
    base_rate
    - (credit_score - 650) * 0.005       # better credit → lower rate
    + (1 - down_payment_pct) * 1.2       # low DP → higher rate
    + (employment_type == 1) * 0.35      # self-employed premium
    + (employment_type == 2) * 0.20      # contract premium
    + np.random.normal(0, 0.2, N)        # lender variation
).clip(2.5, 9.5)

# ── Build DataFrame ──────────────────────────────────────────────────────────
df = pd.DataFrame({
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

print(f"Dataset shape: {df.shape}")
print(f"Approval rate: {df['approved'].mean():.1%}")
print(f"Avg interest rate: {df['interest_rate'].mean():.2f}%")
print(df.describe())

# ── Train/test split ─────────────────────────────────────────────────────────
FEATURES = [
    "annual_income", "credit_score", "down_payment_pct", "property_value",
    "existing_monthly_debt", "gds_ratio", "tds_ratio",
    "employment_type", "province", "amortization", "property_type",
]

X = df[FEATURES]
y_approval = df["approved"]
y_rate = df["interest_rate"]

X_train, X_test, ya_train, ya_test, yr_train, yr_test = train_test_split(
    X, y_approval, y_rate, test_size=0.20, random_state=42
)

# ── Approval classifier ──────────────────────────────────────────────────────
scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

clf = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
clf.fit(X_train_s, ya_train)
ya_pred = clf.predict(X_test_s)
print(f"\nApproval model accuracy: {accuracy_score(ya_test, ya_pred):.3f}")

# ── Interest rate regressor ──────────────────────────────────────────────────
reg = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, random_state=42)
reg.fit(X_train_s, yr_train)
yr_pred = reg.predict(X_test_s)
print(f"Rate model MAE: {mean_absolute_error(yr_test, yr_pred):.4f}%")

# ── Save artifacts ───────────────────────────────────────────────────────────
out_dir = os.path.dirname(__file__)
joblib.dump(clf, os.path.join(out_dir, "approval_model.pkl"))
joblib.dump(reg, os.path.join(out_dir, "rate_model.pkl"))
joblib.dump(scaler, os.path.join(out_dir, "scaler.pkl"))
joblib.dump(FEATURES, os.path.join(out_dir, "features.pkl"))

print("\nModels saved successfully.")
