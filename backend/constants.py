"""Shared constants used by main.py and scheduler.py."""

PROVINCE_MAP = {
    "ON": 0, "BC": 1, "AB": 2, "QC": 3, "MB": 4,
    "SK": 5, "NS": 6, "NB": 7, "NL": 8, "PE": 9,
}

EMPLOYMENT_MAP = {"salaried": 0, "self_employed": 1, "contract": 2}

PROPERTY_TYPE_MAP = {"condo": 0, "house": 1, "townhouse": 2}

FEATURES = [
    "annual_income", "credit_score", "down_payment_pct", "property_value",
    "existing_monthly_debt", "gds_ratio", "tds_ratio",
    "employment_type", "province", "amortization", "property_type",
]

# CMHC rules: min down payment by property value tier
CMHC_TIERS = [
    (500_000,   0.05),
    (1_000_000, 0.10),
    (1_500_000, 0.20),  # max insurable; over $1.5M requires 20% but no CMHC
]

# OSFI B-20 debt service ratio limits
GDS_LIMIT = 0.39
TDS_LIMIT = 0.44

# Stress test floor rate (OSFI B-20)
STRESS_TEST_FLOOR = 5.25
