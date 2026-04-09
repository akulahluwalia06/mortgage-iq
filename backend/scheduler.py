"""
Background scheduler — two jobs:

  storage_guard  (every 30 min)
    Deletes the oldest records when the collection exceeds MAX_DOCS.

  retrain_check  (every 1 hour)
    Retrains models when RETRAIN_THRESHOLD new predictions have accumulated.
    Blends real data with a cached synthetic baseline (catastrophic-forgetting guard).
"""

import logging
import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, mean_absolute_error

from constants import (
    PROVINCE_MAP, EMPLOYMENT_MAP, PROPERTY_TYPE_MAP, FEATURES,
    GDS_LIMIT, TDS_LIMIT, STRESS_TEST_FLOOR,
    compute_gds_tds, generate_synthetic,
)

log = logging.getLogger("scheduler")

# ── Config ────────────────────────────────────────────────────────────────────
MAX_DOCS          = int(os.getenv("MAX_DOCS",          150_000))
TARGET_DOCS       = int(os.getenv("TARGET_DOCS",       100_000))
RETRAIN_THRESHOLD = int(os.getenv("RETRAIN_THRESHOLD", 500))
MODEL_DIR         = os.path.join(os.path.dirname(__file__), "model")

_last_retrain_ts: datetime = datetime.now(timezone.utc) - timedelta(days=365)
_synthetic_cache: pd.DataFrame | None = None


# ── Job 1: Storage guard ──────────────────────────────────────────────────────
async def storage_guard(col):
    try:
        count = await col.count_documents({})
        log.info(f"[storage_guard] {count:,} docs (limit={MAX_DOCS:,})")
        if count <= MAX_DOCS:
            return
        delete_n = count - TARGET_DOCS
        cursor = col.find({}, {"_id": 1}).sort("timestamp", 1).skip(delete_n - 1).limit(1)
        docs   = await cursor.to_list(length=1)
        if not docs:
            return
        result = await col.delete_many({"_id": {"$lte": docs[0]["_id"]}})
        log.info(f"[storage_guard] deleted {result.deleted_count:,} records")
    except Exception as e:
        log.error(f"[storage_guard] failed: {e}")


# ── Synthetic baseline (cached per process) ───────────────────────────────────
def _get_synthetic_baseline(n: int = 3_000) -> pd.DataFrame:
    global _synthetic_cache
    if _synthetic_cache is None:
        log.info(f"[scheduler] generating synthetic baseline ({n} samples)")
        _synthetic_cache = generate_synthetic(n=n, seed=99)
    return _synthetic_cache


# ── Convert stored documents → training DataFrame ─────────────────────────────
def _docs_to_df(docs: list) -> pd.DataFrame:
    rows = []
    for d in docs:
        inp = d.get("input", {})
        res = d.get("result", {})
        try:
            pv   = float(inp["property_value"])
            dp   = float(inp["down_payment"])
            inc  = float(inp["annual_income"])
            debt = float(inp.get("existing_monthly_debt", 0))
            if pv <= 0 or inc <= 0:
                continue

            loan   = pv - dp
            amort  = int(inp.get("amortization", 25))
            gds, tds = compute_gds_tds(loan, pv, inc, debt, amort)

            rows.append({
                "annual_income":         inc,
                "credit_score":          int(inp["credit_score"]),
                "down_payment_pct":      dp / pv,
                "property_value":        pv,
                "existing_monthly_debt": debt,
                "gds_ratio":             gds,
                "tds_ratio":             tds,
                "employment_type":       EMPLOYMENT_MAP.get(inp.get("employment_type", "salaried"), 0),
                "province":              PROVINCE_MAP.get(inp.get("province", "ON"), 0),
                "amortization":          amort,
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

        cursor  = col.find(
            {"timestamp": {"$gt": _last_retrain_ts}},
            {"_id": 0, "input": 1, "result": 1},
        )
        docs    = await cursor.to_list(length=None)
        real_df = _docs_to_df(docs)
        log.info(f"[retrain_check] {len(real_df)} usable real records")

        if len(real_df) < 50:
            log.warning("[retrain_check] too few usable records — skipping")
            return

        synth_df = _get_synthetic_baseline(n=max(3_000, len(real_df) // 2))
        df       = pd.concat([real_df, synth_df], ignore_index=True).sample(frac=1, random_state=42)
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

        joblib.dump(clf,        os.path.join(MODEL_DIR, "approval_model.pkl"))
        joblib.dump(reg,        os.path.join(MODEL_DIR, "rate_model.pkl"))
        joblib.dump(new_scaler, os.path.join(MODEL_DIR, "scaler.pkl"))

        app_state["approval_model"] = clf
        app_state["rate_model"]     = reg
        app_state["scaler"]         = new_scaler

        _last_retrain_ts = datetime.now(timezone.utc)
        log.info("[retrain_check] models hot-swapped ✅")

    except Exception as e:
        log.error(f"[retrain_check] failed: {e}")


# ── Register jobs ─────────────────────────────────────────────────────────────
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
