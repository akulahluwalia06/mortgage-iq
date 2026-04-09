"""
Shared constants and pure utility functions for the Canadian Mortgage Predictor.

This is the single source of truth for:
  - Feature/encoding maps (used by API, scheduler, and training)
  - CMHC rules and ratio limits
  - Financial helper functions (used by API and scheduler)
  - Synthetic data generation (used by initial training and scheduler)
"""

import numpy as np
import pandas as pd

# ── Encoding maps ─────────────────────────────────────────────────────────────
PROVINCE_MAP = {
    "ON": 0, "BC": 1, "AB": 2, "QC": 3, "MB": 4,
    "SK": 5, "NS": 6, "NB": 7, "NL": 8, "PE": 9,
}

EMPLOYMENT_MAP     = {"salaried": 0, "self_employed": 1, "contract": 2}
PROPERTY_TYPE_MAP  = {"condo": 0, "house": 1, "townhouse": 2}

FEATURES = [
    "annual_income", "credit_score", "down_payment_pct", "property_value",
    "existing_monthly_debt", "gds_ratio", "tds_ratio",
    "employment_type", "province", "amortization", "property_type",
]

# ── Province median home prices (2023 CREA, CAD) ──────────────────────────────
PROVINCE_MEDIAN_PRICE = {
    0: 850_000,   # ON
    1: 950_000,   # BC
    2: 450_000,   # AB
    3: 420_000,   # QC
    4: 340_000,   # MB
    5: 315_000,   # SK
    6: 375_000,   # NS
    7: 265_000,   # NB
    8: 280_000,   # NL
    9: 295_000,   # PE
}

# ── CMHC rules ────────────────────────────────────────────────────────────────
# Minimum down payment tiers: (max_property_value, pct_on_this_tier)
# For properties $500k–$999k: 5% on first $500k + 10% on the remainder.
# Properties ≥ $1M: 20% flat (uninsurable under CMHC).
# Properties > $1.5M: 20% flat, no CMHC insurance available.
CMHC_MAX_INSURABLE   = 1_500_000
CMHC_TIER_BREAKPOINT = 500_000
CMHC_RATE_LOW        = 0.05    # < $500k or first $500k of larger purchase
CMHC_RATE_MID        = 0.10    # $500k–$999k portion
CMHC_RATE_HIGH       = 0.20    # ≥ $1M

# CMHC premium rates by LTV (loan-to-value) ratio
# LTV = (property_value - down_payment) / property_value
CMHC_PREMIUM_TIERS = [
    (0.80, 0.0280),   # LTV ≤ 80%  (down payment ≥ 20%) → no CMHC (caught before lookup)
    (0.85, 0.0280),   # LTV ≤ 85%  (down payment ≥ 15%)
    (0.90, 0.0310),   # LTV ≤ 90%  (down payment ≥ 10%)
    (0.95, 0.0400),   # LTV ≤ 95%  (down payment ≥ 5%)
]

# ── Ratio limits & stress test ────────────────────────────────────────────────
GDS_LIMIT          = 0.39
TDS_LIMIT          = 0.44
STRESS_TEST_FLOOR  = 5.25   # OSFI B-20 minimum qualifying rate (%)

# ── Rate bounds ───────────────────────────────────────────────────────────────
RATE_MIN = 2.5
RATE_MAX = 9.5

# ── Property cost estimate ────────────────────────────────────────────────────
# Rough annual property tax + heat as a fraction of property value (monthly)
PROPERTY_TAX_HEAT_RATE = 0.015 / 12   # ≈ 1.5% annual, divided to monthly

# ── CAD/USD conversion (for dataset normalisation) ───────────────────────────
CAD_USD_RATE = 1.36


# ── Pure financial functions ──────────────────────────────────────────────────

def monthly_payment(principal: float, annual_rate_pct: float, years: int) -> float:
    """Standard fixed-rate amortisation payment formula."""
    r = (annual_rate_pct / 100) / 12
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def cmhc_insurance(property_value: float, down_payment: float) -> float:
    """CMHC mortgage default insurance per current CMHC premium schedule."""
    if property_value > CMHC_MAX_INSURABLE:
        return 0.0
    dp_pct = down_payment / property_value
    if dp_pct >= 0.20:
        return 0.0
    ltv = 1 - dp_pct
    for ltv_ceiling, rate in CMHC_PREMIUM_TIERS:
        if ltv <= ltv_ceiling:
            return round((property_value - down_payment) * rate, 2)
    return round((property_value - down_payment) * CMHC_PREMIUM_TIERS[-1][1], 2)


def min_down_payment(property_value: float) -> float:
    """CMHC-mandated minimum down payment (pro-rated for $500k–$999k)."""
    if property_value >= 1_000_000:
        return property_value * CMHC_RATE_HIGH
    if property_value <= CMHC_TIER_BREAKPOINT:
        return property_value * CMHC_RATE_LOW
    return (CMHC_TIER_BREAKPOINT * CMHC_RATE_LOW
            + (property_value - CMHC_TIER_BREAKPOINT) * CMHC_RATE_MID)


def compute_gds_tds(
    loan: float,
    property_value: float,
    annual_income: float,
    existing_monthly_debt: float,
    amortization_years: int,
    qualifying_rate: float = STRESS_TEST_FLOOR,
) -> tuple[float, float]:
    """
    Compute Gross Debt Service (GDS) and Total Debt Service (TDS) ratios
    using a given qualifying rate (defaults to the stress-test floor).

    Returns (gds, tds).
    """
    est_payment   = monthly_payment(loan, qualifying_rate, amortization_years)
    prop_tax_heat = property_value * PROPERTY_TAX_HEAT_RATE
    monthly_income = annual_income / 12
    gds = (est_payment + prop_tax_heat) / monthly_income
    tds = gds + existing_monthly_debt / monthly_income
    return gds, tds


# ── Synthetic data generator ──────────────────────────────────────────────────

def generate_synthetic(n: int = 20_000, seed: int = 42) -> pd.DataFrame:
    """
    Generate synthetic Canadian mortgage training data calibrated to:
      - StatsCan 2023 income distribution (log-normal)
      - CREA 2023 provincial median prices
      - CMHC minimum down payment rules
      - Bank of Canada 2018–2024 rate cycle
    """
    rng = np.random.default_rng(seed)

    province        = rng.choice(list(PROVINCE_MEDIAN_PRICE.keys()), n)
    employment_type = rng.choice([0, 1, 2], n, p=[0.65, 0.20, 0.15])
    property_type   = rng.choice([0, 1, 2], n, p=[0.30, 0.55, 0.15])
    amortization    = rng.choice([15, 20, 25, 30], n, p=[0.10, 0.20, 0.55, 0.15])
    annual_income   = rng.lognormal(11.3, 0.45, n).clip(35_000, 500_000)
    credit_score    = rng.normal(680, 80, n).clip(300, 900).astype(int)

    base_price     = np.array([PROVINCE_MEDIAN_PRICE[p] for p in province])
    property_value = (base_price * rng.lognormal(0, 0.35, n)).clip(150_000, 3_000_000)

    min_dp_pct = np.vectorize(lambda pv: min_down_payment(pv) / pv)(property_value)
    down_pct   = (min_dp_pct + rng.exponential(0.08, n)).clip(min_dp_pct, 0.80)
    debt       = rng.exponential(400, n).clip(0, 4_000)

    loan = property_value * (1 - down_pct)
    gds, tds = np.vectorize(
        lambda l, pv, inc, d, am: compute_gds_tds(l, pv, inc, d, am)
    )(loan, property_value, annual_income, debt, amortization)

    approved = (
        (credit_score >= 600)
        & (gds <= GDS_LIMIT)
        & (tds <= TDS_LIMIT)
        & (down_pct >= min_dp_pct)
        & (annual_income >= 40_000)
        & ~((employment_type == 1) & (credit_score < 650))
    ).astype(int)
    approved ^= (rng.random(n) < 0.05).astype(int)

    rate = (
        5.5
        - (credit_score - 650) * 0.005
        + (1 - down_pct) * 1.2
        + (employment_type == 1) * 0.35
        + (employment_type == 2) * 0.20
        + rng.normal(0, 0.2, n)
    ).clip(RATE_MIN, RATE_MAX)

    return pd.DataFrame({
        "annual_income":         annual_income,
        "credit_score":          credit_score,
        "down_payment_pct":      down_pct,
        "property_value":        property_value,
        "existing_monthly_debt": debt,
        "gds_ratio":             gds,
        "tds_ratio":             tds,
        "employment_type":       employment_type,
        "province":              province,
        "amortization":          amortization,
        "property_type":         property_type,
        "approved":              approved,
        "interest_rate":         rate,
    })
