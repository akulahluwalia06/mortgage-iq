"""
Background scheduler — two jobs:

  1. storage_guard  (every 30 min)
     Checks how many documents are in the predictions collection.
     If count > MAX_DOCS, deletes the oldest (count - TARGET_DOCS) records.
     Atlas M0 free tier: 512 MB total. Each prediction doc ≈ 2–3 KB.
     Defaults: MAX_DOCS=150_000  TARGET_DOCS=100_000

  2. retrain_check  (every 1 hour)
     Counts records added since the last retrain.
     If new records >= RETRAIN_THRESHOLD, pulls data from MongoDB,
     merges with a small synthetic baseline (prevents catastrophic forgetting),
     retrains both models, saves .pkl files, and hot-swaps them in memory.
"""

import logging
import os
import io
import numpy as np
import pandas as pd
import joblib
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error

log = logging.getLogger("scheduler")

# ── Config (override via .env) ────────────────────────────────────────────────
MAX_DOCS        = int(os.getenv("MAX_DOCS", 150_000))   # purge trigger
TARGET_DOCS     = int(os.getenv("TARGET_DOCS", 100_000)) # keep this many after purge
RETRAIN_THRESHOLD = int(os.getenv("RETRAIN_THRESHOLD", 500))  # new records before retrain
MODEL_DIR       = os.path.join(os.path.dirname(__file__), "model")

FEATURES = [
    "annual_income", "credit_score", "down_payment_pct", "property_value",
    "existing_monthly_debt", "gds_ratio", "tds_ratio",
    "employment_type", "province", "amortization", "property_type",
]

PROVINCE_MAP    = {"ON":0,"BC":1,"AB":2,"QC":3,"MB":4,"SK":5,"NS":6,"NB":7,"NL":8,"PE":9}
EMPLOYMENT_MAP  = {"salaried":0,"self_employed":1,"contract":2}
PROPERTY_MAP    = {"condo":0,"house":1,"townhouse":2}

# Tracks the timestamp of the last retrain so we count only NEW records
_last_retrain_ts: datetime = datetime.now(timezone.utc) - timedelta(days=365)


# ── Job 1: Storage guard ──────────────────────────────────────────────────────
async def storage_guard(col):
    count = await col.count_documents({})
    log.info(f"[storage_guard] collection has {count:,} documents (max={MAX_DOCS:,})")

    if count <= MAX_DOCS:
        return

    delete_n = count - TARGET_DOCS
    log.warning(f"[storage_guard] over limit — deleting {delete_n:,} oldest records")

    # Find the _id of the Nth oldest document
    cursor = col.find({}, {"_id": 1}).sort("timestamp", 1).skip(delete_n - 1).limit(1)
    docs = await cursor.to_list(length=1)
    if not docs:
        return

    cutoff_id = docs[0]["_id"]
    result = await col.delete_many({"_id": {"$lte": cutoff_id}})
    log.info(f"[storage_guard] deleted {result.deleted_count:,} records")


# ── Synthetic baseline (prevents catastrophic forgetting) ─────────────────────
def _synthetic_baseline(n=3000, seed=99):
    """Small synthetic dataset to blend with real records during retraining."""
    np.random.seed(seed)
    PROVINCE_MEDIAN = {0:850000,1:950000,2:450000,3:420000,4:340000,
                       5:315000,6:375000,7:265000,8:280000,9:295000}
    province        = np.random.choice(10, n)
    employment_type = np.random.choice([0,1,2], n, p=[0.65,0.20,0.15])
    property_type   = np.random.choice([0,1,2], n, p=[0.30,0.55,0.15])
    amortization    = np.random.choice([15,20,25,30], n, p=[0.10,0.20,0.55,0.15])
    annual_income   = np.random.lognormal(11.3, 0.45, n).clip(35000, 500000)
    credit_score    = np.random.normal(680, 80, n).clip(300, 900).astype(int)
    base_price      = np.array([PROVINCE_MEDIAN[p] for p in province])
    property_value  = (base_price * np.random.lognormal(0, 0.35, n)).clip(150000, 3000000)
    min_dp = np.where(property_value<500000, 0.05,
              np.where(property_value<1000000, 0.10, 0.20))
    down_payment_pct = (min_dp + np.random.exponential(0.08, n)).clip(min_dp, 0.80)
    existing_monthly_debt = np.random.exponential(400, n).clip(0, 4000)
    monthly_income  = annual_income / 12
    est_payment     = (property_value * (1 - down_payment_pct)) * 0.005
    gds_ratio       = (est_payment + 300) / monthly_income
    tds_ratio       = gds_ratio + existing_monthly_debt / monthly_income
    approved = (
        (credit_score >= 600) & (gds_ratio <= 0.39) & (tds_ratio <= 0.44) &
        (annual_income >= 40000) & ~((employment_type==1) & (credit_score<650))
    ).astype(int)
    approved ^= (np.random.random(n) < 0.05)
    rate = (5.5 - (credit_score-650)*0.005 + (1-down_payment_pct)*1.2
            + (employment_type==1)*0.35 + (employment_type==2)*0.20
            + np.random.normal(0, 0.2, n)).clip(2.5, 9.5)

    return pd.DataFrame({
        "annual_income": annual_income, "credit_score": credit_score,
        "down_payment_pct": down_payment_pct, "property_value": property_value,
        "existing_monthly_debt": existing_monthly_debt,
        "gds_ratio": gds_ratio, "tds_ratio": tds_ratio,
        "employment_type": employment_type, "province": province,
        "amortization": amortization, "property_type": property_type,
        "approved": approved, "interest_rate": rate,
    })


def _mongo_docs_to_df(docs: list) -> pd.DataFrame:
    """Convert stored prediction documents to a training DataFrame."""
    rows = []
    for d in docs:
        inp = d.get("input", {})
        res = d.get("result", {})
        try:
            pv   = float(inp["property_value"])
            dp   = float(inp["down_payment"])
            inc  = float(inp["annual_income"])
            debt = float(inp.get("existing_monthly_debt", 0))
            # Recompute derived features (same logic as main.py)
            dp_pct  = dp / pv
            loan    = pv - dp
            r_stress = 5.25
            monthly_income = inc / 12
            est_pmt = loan * (r_stress/100/12 * (1+r_stress/100/12)**300) / ((1+r_stress/100/12)**300 - 1)
            prop_tax = pv * 0.015 / 12
            gds = (est_pmt + prop_tax) / monthly_income
            tds = gds + debt / monthly_income

            rows.append({
                "annual_income":        inc,
                "credit_score":         int(inp["credit_score"]),
                "down_payment_pct":     dp_pct,
                "property_value":       pv,
                "existing_monthly_debt": debt,
                "gds_ratio":            gds,
                "tds_ratio":            tds,
                "employment_type":      EMPLOYMENT_MAP.get(inp.get("employment_type","salaried"), 0),
                "province":             PROVINCE_MAP.get(inp.get("province","ON"), 0),
                "amortization":         int(inp.get("amortization", 25)),
                "property_type":        PROPERTY_MAP.get(inp.get("property_type","house"), 1),
                "approved":             1 if res.get("approved") else 0,
                "interest_rate":        float(res.get("predicted_interest_rate", 5.5)),
            })
        except (KeyError, TypeError, ZeroDivisionError):
            continue
    return pd.DataFrame(rows)


# ── Job 2: Retrain check ──────────────────────────────────────────────────────
async def retrain_check(col, app_state: dict):
    global _last_retrain_ts

    new_count = await col.count_documents({"timestamp": {"$gt": _last_retrain_ts}})
    log.info(f"[retrain_check] {new_count} new records since last retrain (threshold={RETRAIN_THRESHOLD})")

    if new_count < RETRAIN_THRESHOLD:
        return

    log.info("[retrain_check] threshold reached — starting retraining")

    # Pull all records from MongoDB
    cursor = col.find({}, {"_id": 0, "input": 1, "result": 1})
    docs   = await cursor.to_list(length=None)
    real_df = _mongo_docs_to_df(docs)
    log.info(f"[retrain_check] {len(real_df)} usable real records loaded")

    # Blend with synthetic baseline to prevent catastrophic forgetting
    synth_df = _synthetic_baseline(n=max(3000, len(real_df) // 2))
    df = pd.concat([real_df, synth_df], ignore_index=True)
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    log.info(f"[retrain_check] training on {len(df)} total samples ({len(real_df)} real + {len(synth_df)} synthetic)")

    X = df[FEATURES]
    y_approval = df["approved"]
    y_rate     = df["interest_rate"]

    X_train, X_test, ya_train, ya_test, yr_train, yr_test = train_test_split(
        X, y_approval, y_rate, test_size=0.20, random_state=42
    )

    scaler   = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)

    clf = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
    clf.fit(X_train_s, ya_train)
    acc = accuracy_score(ya_test, clf.predict(X_test_s))

    reg = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, random_state=42)
    reg.fit(X_train_s, yr_train)
    mae = mean_absolute_error(yr_test, reg.predict(X_test_s))

    log.info(f"[retrain_check] approval accuracy={acc:.3f}  rate MAE={mae:.4f}%")

    # Save new model files
    joblib.dump(clf,    os.path.join(MODEL_DIR, "approval_model.pkl"))
    joblib.dump(reg,    os.path.join(MODEL_DIR, "rate_model.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.pkl"))

    # Hot-swap in memory (no restart needed)
    app_state["approval_model"] = clf
    app_state["rate_model"]     = reg
    app_state["scaler"]         = scaler

    _last_retrain_ts = datetime.now(timezone.utc)
    log.info(f"[retrain_check] models hot-swapped ✅  next retrain window starts now")


# ── Register scheduler ────────────────────────────────────────────────────────
def start_scheduler(col, app_state: dict) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        storage_guard,
        trigger="interval",
        minutes=30,
        args=[col],
        id="storage_guard",
        next_run_time=datetime.now(timezone.utc),   # run once on startup too
    )

    scheduler.add_job(
        retrain_check,
        trigger="interval",
        hours=1,
        args=[col, app_state],
        id="retrain_check",
        next_run_time=datetime.now(timezone.utc),   # check immediately on startup
    )

    scheduler.start()
    log.info(f"[scheduler] started — storage_guard every 30 min, retrain_check every 1 hr")
    return scheduler
