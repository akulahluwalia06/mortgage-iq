"""
Background scheduler — two jobs:

  storage_guard  (every 30 min)
    Deletes the oldest records when the collection exceeds MAX_DOCS.
    Keeps Atlas M0 (512 MB) well within limits.

  retrain_check  (every 1 hour)
    Retrains both models when RETRAIN_THRESHOLD new predictions have
    accumulated since the last run. Blends real data with a cached
    synthetic baseline to prevent catastrophic forgetting.
"""

import logging
import os
import numpy as np
import pandas as pd
import joblib
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error

from constants import PROVINCE_MAP, EMPLOYMENT_MAP, PROPERTY_TYPE_MAP, FEATURES

log = logging.getLogger("scheduler")

# ── Config ────────────────────────────────────────────────────────────────────
MAX_DOCS          = int(os.getenv("MAX_DOCS", 150_000))
TARGET_DOCS       = int(os.getenv("TARGET_DOCS", 100_000))
RETRAIN_THRESHOLD = int(os.getenv("RETRAIN_THRESHOLD", 500))
MODEL_DIR         = os.path.join(os.path.dirname(__file__), "model")

# Timestamp of last successful retrain (far past on first run)
_last_retrain_ts: datetime = datetime.now(timezone.utc) - timedelta(days=365)

# Cached synthetic baseline — generated once per process, reused on every retrain
_synthetic_cache: pd.DataFrame | None = None


# ── Job 1: Storage guard ──────────────────────────────────────────────────────
async def storage_guard(col):
    try:
        count = await col.count_documents({})
        log.info(f"[storage_guard] {count:,} docs (limit={MAX_DOCS:,})")

        if count <= MAX_DOCS:
            return

        delete_n = count - TARGET_DOCS
        # Find the _id cutoff of the Nth oldest doc
        cursor = col.find({}, {"_id": 1}).sort("timestamp", 1).skip(delete_n - 1).limit(1)
        docs = await cursor.to_list(length=1)
        if not docs:
            return

        result = await col.delete_many({"_id": {"$lte": docs[0]["_id"]}})
        log.info(f"[storage_guard] deleted {result.deleted_count:,} records")
    except Exception as e:
        log.error(f"[storage_guard] failed: {e}")


# ── Synthetic baseline (cached) ───────────────────────────────────────────────
def _get_synthetic_baseline(n: int = 3000) -> pd.DataFrame:
    """Return a synthetic baseline DataFrame. Generated once then cached."""
    global _synthetic_cache
    if _synthetic_cache is not None:
        return _synthetic_cache

    log.info(f"[scheduler] generating synthetic baseline ({n} samples)")
    np.random.seed(99)

    PROVINCE_MEDIAN = {0:850_000, 1:950_000, 2:450_000, 3:420_000, 4:340_000,
                       5:315_000, 6:375_000, 7:265_000, 8:280_000, 9:295_000}

    province        = np.random.choice(10, n)
    employment_type = np.random.choice([0, 1, 2], n, p=[0.65, 0.20, 0.15])
    property_type   = np.random.choice([0, 1, 2], n, p=[0.30, 0.55, 0.15])
    amortization    = np.random.choice([15, 20, 25, 30], n, p=[0.10, 0.20, 0.55, 0.15])
    annual_income   = np.random.lognormal(11.3, 0.45, n).clip(35_000, 500_000)
    credit_score    = np.random.normal(680, 80, n).clip(300, 900).astype(int)
    base_price      = np.array([PROVINCE_MEDIAN[p] for p in province])
    property_value  = (base_price * np.random.lognormal(0, 0.35, n)).clip(150_000, 3_000_000)

    min_dp = np.where(property_value < 500_000, 0.05,
              np.where(property_value < 1_000_000, 0.10, 0.20))
    down_payment_pct = (min_dp + np.random.exponential(0.08, n)).clip(min_dp, 0.80)
    existing_debt    = np.random.exponential(400, n).clip(0, 4_000)
    monthly_income   = annual_income / 12
    est_payment      = (property_value * (1 - down_payment_pct)) * 0.005
    gds_ratio        = (est_payment + 300) / monthly_income
    tds_ratio        = gds_ratio + existing_debt / monthly_income

    approved = (
        (credit_score >= 600) & (gds_ratio <= 0.39) & (tds_ratio <= 0.44) &
        (annual_income >= 40_000) & ~((employment_type == 1) & (credit_score < 650))
    ).astype(int)
    approved ^= (np.random.random(n) < 0.05)

    rate = (5.5 - (credit_score - 650) * 0.005 + (1 - down_payment_pct) * 1.2
            + (employment_type == 1) * 0.35 + (employment_type == 2) * 0.20
            + np.random.normal(0, 0.2, n)).clip(2.5, 9.5)

    _synthetic_cache = pd.DataFrame({
        "annual_income": annual_income, "credit_score": credit_score,
        "down_payment_pct": down_payment_pct, "property_value": property_value,
        "existing_monthly_debt": existing_debt, "gds_ratio": gds_ratio,
        "tds_ratio": tds_ratio, "employment_type": employment_type,
        "province": province, "amortization": amortization,
        "property_type": property_type, "approved": approved, "interest_rate": rate,
    })
    return _synthetic_cache


def _docs_to_df(docs: list) -> pd.DataFrame:
    """Convert stored prediction documents into a training-ready DataFrame."""
    rows = []
    for d in docs:
        inp = d.get("input", {})
        res = d.get("result", {})
        try:
            pv    = float(inp["property_value"])
            dp    = float(inp["down_payment"])
            inc   = float(inp["annual_income"])
            debt  = float(inp.get("existing_monthly_debt", 0))
            if pv <= 0 or inc <= 0:
                continue

            dp_pct = dp / pv
            loan   = pv - dp
            # Reproduce GDS/TDS using same formula as main.py
            r = (5.25 / 100) / 12
            n = int(inp.get("amortization", 25)) * 12
            est_pmt = loan * (r * (1 + r) ** n) / ((1 + r) ** n - 1) if r else loan / n
            prop_tax = pv * 0.015 / 12
            monthly_income = inc / 12
            gds = (est_pmt + prop_tax) / monthly_income
            tds = gds + debt / monthly_income

            rows.append({
                "annual_income":         inc,
                "credit_score":          int(inp["credit_score"]),
                "down_payment_pct":      dp_pct,
                "property_value":        pv,
                "existing_monthly_debt": debt,
                "gds_ratio":             gds,
                "tds_ratio":             tds,
                "employment_type":       EMPLOYMENT_MAP.get(inp.get("employment_type", "salaried"), 0),
                "province":              PROVINCE_MAP.get(inp.get("province", "ON"), 0),
                "amortization":          int(inp.get("amortization", 25)),
                "property_type":         PROPERTY_TYPE_MAP.get(inp.get("property_type", "house"), 1),
                "approved":              1 if res.get("approved") else 0,
                "interest_rate":         float(res.get("predicted_interest_rate", 5.5)),
            })
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            continue
    return pd.DataFrame(rows)


# ── Job 2: Retrain check ──────────────────────────────────────────────────────
async def retrain_check(col, app_state: dict):
    global _last_retrain_ts

    try:
        new_count = await col.count_documents({"timestamp": {"$gt": _last_retrain_ts}})
        log.info(f"[retrain_check] {new_count} new records since last retrain (threshold={RETRAIN_THRESHOLD})")

        if new_count < RETRAIN_THRESHOLD:
            return

        log.info("[retrain_check] threshold reached — starting retraining")

        # Only fetch records since last retrain to cap memory usage
        cursor = col.find(
            {"timestamp": {"$gt": _last_retrain_ts}},
            {"_id": 0, "input": 1, "result": 1}
        )
        docs = await cursor.to_list(length=None)
        real_df = _docs_to_df(docs)
        log.info(f"[retrain_check] {len(real_df)} usable real records")

        if len(real_df) < 50:
            log.warning("[retrain_check] too few usable records after parsing — skipping")
            return

        # Blend with cached synthetic baseline
        synth_df = _get_synthetic_baseline(n=max(3000, len(real_df) // 2))
        df = pd.concat([real_df, synth_df], ignore_index=True).sample(frac=1, random_state=42)
        log.info(f"[retrain_check] training on {len(df)} total ({len(real_df)} real + {len(synth_df)} synthetic)")

        X  = df[FEATURES]
        ya = df["approved"]
        yr = df["interest_rate"]

        X_train, X_test, ya_train, ya_test, yr_train, yr_test = train_test_split(
            X, ya, yr, test_size=0.20, random_state=42
        )

        new_scaler = StandardScaler()
        X_train_s  = new_scaler.fit_transform(X_train)
        X_test_s   = new_scaler.transform(X_test)

        clf = RandomForestClassifier(n_estimators=200, max_depth=12, random_state=42, n_jobs=-1)
        clf.fit(X_train_s, ya_train)
        acc = accuracy_score(ya_test, clf.predict(X_test_s))

        reg = GradientBoostingRegressor(n_estimators=300, max_depth=5, learning_rate=0.05, random_state=42)
        reg.fit(X_train_s, yr_train)
        mae = mean_absolute_error(yr_test, reg.predict(X_test_s))

        log.info(f"[retrain_check] accuracy={acc:.3f}  rate_MAE={mae:.4f}%")

        # Persist to disk
        joblib.dump(clf,        os.path.join(MODEL_DIR, "approval_model.pkl"))
        joblib.dump(reg,        os.path.join(MODEL_DIR, "rate_model.pkl"))
        joblib.dump(new_scaler, os.path.join(MODEL_DIR, "scaler.pkl"))

        # Hot-swap in memory — no server restart needed
        app_state["approval_model"] = clf
        app_state["rate_model"]     = reg
        app_state["scaler"]         = new_scaler

        _last_retrain_ts = datetime.now(timezone.utc)
        log.info("[retrain_check] models hot-swapped ✅")

    except Exception as e:
        log.error(f"[retrain_check] failed: {e}")


# ── Register scheduler ────────────────────────────────────────────────────────
def start_scheduler(col, app_state: dict) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        storage_guard, trigger="interval", minutes=30,
        args=[col], id="storage_guard",
        next_run_time=datetime.now(timezone.utc),
    )
    scheduler.add_job(
        retrain_check, trigger="interval", hours=1,
        args=[col, app_state], id="retrain_check",
        next_run_time=datetime.now(timezone.utc),
    )

    scheduler.start()
    log.info("[scheduler] started — storage_guard every 30 min · retrain_check every 1 hr")
    return scheduler
