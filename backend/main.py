"""
Canadian Mortgage Predictor — FastAPI Backend
"""

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from datetime import datetime, timezone
import numpy as np
import joblib
import os
import logging

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from constants import (
    PROVINCE_MAP, EMPLOYMENT_MAP, PROPERTY_TYPE_MAP,
    GDS_LIMIT, TDS_LIMIT, STRESS_TEST_FLOOR,
)
from scheduler import start_scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Canadian Mortgage Predictor API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Load models ───────────────────────────────────────────────────────────────
MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")

try:
    approval_model = joblib.load(os.path.join(MODEL_DIR, "approval_model.pkl"))
    rate_model     = joblib.load(os.path.join(MODEL_DIR, "rate_model.pkl"))
    scaler         = joblib.load(os.path.join(MODEL_DIR, "scaler.pkl"))
    log.info("✅ Models loaded successfully")
except FileNotFoundError:
    log.warning("⚠️  Models not found. Run model/train_model.py first.")
    approval_model = rate_model = scaler = None

# ── MongoDB setup ─────────────────────────────────────────────────────────────
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME     = os.getenv("DB_NAME", "mortgage_predictor")

db_client: AsyncIOMotorClient | None = None
predictions_col = None
_scheduler = None

# Shared mutable state — scheduler hot-swaps models here without restart
app_state: dict = {}


@app.on_event("startup")
async def startup_db():
    global db_client, predictions_col, _scheduler
    if MONGODB_URI:
        db_client = AsyncIOMotorClient(MONGODB_URI)
        db = db_client[DB_NAME]
        predictions_col = db["predictions"]
        await predictions_col.create_index("timestamp")
        log.info(f"✅ MongoDB connected → {DB_NAME}.predictions")

        app_state["approval_model"] = approval_model
        app_state["rate_model"]     = rate_model
        app_state["scaler"]         = scaler
        _scheduler = start_scheduler(predictions_col, app_state)
    else:
        log.warning("⚠️  MONGODB_URI not set — predictions will not be stored.")


@app.on_event("shutdown")
async def shutdown_db():
    if _scheduler:
        _scheduler.shutdown(wait=False)
    if db_client:
        db_client.close()


async def save_prediction(input_data: dict, result_data: dict):
    """Persist a prediction to MongoDB. Silently skips if DB not configured."""
    if predictions_col is None:
        return
    try:
        doc = {
            "timestamp": datetime.now(timezone.utc),
            "input": input_data,
            "result": {k: result_data[k] for k in (
                "approval_probability", "approved", "predicted_interest_rate",
                "monthly_payment", "total_payment", "total_interest",
                "cmhc_insurance", "loan_amount", "gds_ratio", "tds_ratio",
                "passes_stress_test",
            )},
        }
        await predictions_col.insert_one(doc)
    except Exception as e:
        log.warning(f"MongoDB write failed: {e}")


# ── Request / Response schemas ────────────────────────────────────────────────
class MortgageRequest(BaseModel):
    annual_income:         float = Field(..., gt=0,   description="Annual gross income in CAD")
    credit_score:          int   = Field(..., ge=300, le=900, description="Credit score (300–900)")
    property_value:        float = Field(..., gt=0,   description="Property purchase price in CAD")
    down_payment:          float = Field(..., gt=0,   description="Down payment amount in CAD")
    existing_monthly_debt: float = Field(0,  ge=0,   description="Existing monthly debt payments")
    employment_type:       str   = Field(..., description="salaried | self_employed | contract")
    province:              str   = Field(..., description="Province code e.g. ON, BC")
    amortization:          int   = Field(25,          description="Amortization period in years")
    property_type:         str   = Field("house",     description="condo | house | townhouse")

    @validator("province")
    def province_valid(cls, v):
        v = v.upper()
        if v not in PROVINCE_MAP:
            raise ValueError(f"Province must be one of {list(PROVINCE_MAP.keys())}")
        return v

    @validator("employment_type")
    def employment_valid(cls, v):
        if v not in EMPLOYMENT_MAP:
            raise ValueError(f"Employment type must be one of {list(EMPLOYMENT_MAP.keys())}")
        return v

    @validator("property_type")
    def property_type_valid(cls, v):
        if v not in PROPERTY_TYPE_MAP:
            raise ValueError(f"Property type must be one of {list(PROPERTY_TYPE_MAP.keys())}")
        return v

    @validator("amortization")
    def amortization_valid(cls, v):
        if v not in (15, 20, 25, 30):
            raise ValueError("Amortization must be 15, 20, 25, or 30 years")
        return v

    @validator("down_payment")
    def down_payment_valid(cls, v, values):
        pv = values.get("property_value")
        if pv and v >= pv:
            raise ValueError("Down payment must be less than the property value")
        return v


class AmortizationRow(BaseModel):
    year:              int
    principal_paid:    float
    interest_paid:     float
    remaining_balance: float


class MortgageResponse(BaseModel):
    approval_probability:   float
    approved:               bool
    predicted_interest_rate: float
    monthly_payment:        float
    total_payment:          float
    total_interest:         float
    cmhc_insurance:         float
    loan_amount:            float
    gds_ratio:              float
    tds_ratio:              float
    stress_test_rate:       float
    passes_stress_test:     bool
    amortization_schedule:  list[AmortizationRow]
    insights:               list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────
def calculate_cmhc(property_value: float, down_payment: float) -> float:
    """CMHC mortgage insurance per current CMHC rules."""
    dp_pct = down_payment / property_value
    if dp_pct >= 0.20 or property_value > 1_500_000:
        return 0.0
    rate = 0.0400 if dp_pct < 0.10 else 0.0310 if dp_pct < 0.15 else 0.0280
    return round((property_value - down_payment) * rate, 2)


def monthly_payment_calc(principal: float, annual_rate_pct: float, years: int) -> float:
    """Standard fixed-rate monthly mortgage payment formula."""
    r = (annual_rate_pct / 100) / 12
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


def build_amortization_schedule(
    principal: float, annual_rate_pct: float, years: int
) -> list[AmortizationRow]:
    """Year-by-year amortization summary. Payment is computed once for efficiency."""
    r = (annual_rate_pct / 100) / 12
    payment = monthly_payment_calc(principal, annual_rate_pct, years)
    balance = principal
    schedule = []
    for year in range(1, years + 1):
        year_interest = year_principal = 0.0
        for _ in range(12):
            interest = balance * r
            prin = payment - interest
            year_interest  += interest
            year_principal += prin
            balance = max(balance - prin, 0.0)
        schedule.append(AmortizationRow(
            year=year,
            principal_paid=round(year_principal, 2),
            interest_paid=round(year_interest, 2),
            remaining_balance=round(balance, 2),
        ))
    return schedule


# ── Prediction endpoint ───────────────────────────────────────────────────────
@app.post("/predict", response_model=MortgageResponse)
@limiter.limit("10/minute")
async def predict_mortgage(request: Request, req: MortgageRequest):
    if approval_model is None:
        raise HTTPException(503, "Models not loaded. Run model/train_model.py first.")

    monthly_income   = req.annual_income / 12
    down_payment_pct = req.down_payment / req.property_value
    loan_amount      = req.property_value - req.down_payment
    cmhc             = calculate_cmhc(req.property_value, req.down_payment)
    total_loan       = loan_amount + cmhc

    # GDS / TDS computed at stress test floor for qualification purposes
    est_payment      = monthly_payment_calc(total_loan, STRESS_TEST_FLOOR, req.amortization)
    property_tax_heat = req.property_value * 0.015 / 12  # approx 1.5% annual property tax + heat
    gds = (est_payment + property_tax_heat) / monthly_income
    tds = gds + req.existing_monthly_debt / monthly_income

    feature_vector = np.array([[
        req.annual_income,
        req.credit_score,
        down_payment_pct,
        req.property_value,
        req.existing_monthly_debt,
        gds,
        tds,
        EMPLOYMENT_MAP[req.employment_type],
        PROVINCE_MAP[req.province],
        req.amortization,
        PROPERTY_TYPE_MAP[req.property_type],
    ]])

    # Use hot-swapped models when available
    _approval_model = app_state.get("approval_model", approval_model)
    _rate_model     = app_state.get("rate_model", rate_model)
    _scaler         = app_state.get("scaler", scaler)

    try:
        X_scaled      = _scaler.transform(feature_vector)
        approval_prob = float(_approval_model.predict_proba(X_scaled)[0][1])
        predicted_rate = float(_rate_model.predict(X_scaled)[0])
    except Exception as e:
        log.error(f"Model prediction failed: {e}")
        raise HTTPException(500, "Prediction failed. Please try again.")

    predicted_rate = round(max(2.5, min(9.5, predicted_rate)), 2)

    monthly       = monthly_payment_calc(total_loan, predicted_rate, req.amortization)
    total_payment = monthly * req.amortization * 12
    total_interest = total_payment - total_loan

    # OSFI B-20 stress test: qualifying rate is max(contracted_rate + 2%, floor)
    # Capped at 9.5% — beyond that no product exists in Canada
    stress_test_rate = round(min(max(predicted_rate + 2.0, STRESS_TEST_FLOOR), 9.5), 2)
    stress_payment   = monthly_payment_calc(total_loan, stress_test_rate, req.amortization)
    stress_gds       = (stress_payment + property_tax_heat) / monthly_income
    stress_tds       = stress_gds + req.existing_monthly_debt / monthly_income
    passes_stress_test = stress_gds <= GDS_LIMIT and stress_tds <= TDS_LIMIT

    schedule = build_amortization_schedule(total_loan, predicted_rate, req.amortization)

    insights = []
    if approval_prob < 0.5:
        insights.append("⚠️ Low approval probability. Consider a larger down payment or improving your credit score.")
    if gds > GDS_LIMIT:
        insights.append(f"⚠️ GDS ratio ({gds:.1%}) exceeds the Canadian standard of {GDS_LIMIT:.0%}. Reduce the property value or increase income.")
    if tds > TDS_LIMIT:
        insights.append(f"⚠️ TDS ratio ({tds:.1%}) exceeds the Canadian standard of {TDS_LIMIT:.0%}. Paying down existing debts will help.")
    if not passes_stress_test:
        insights.append("⚠️ Does not pass the Canadian mortgage stress test (OSFI B-20). You must qualify at the stress test rate.")
    if cmhc > 0:
        insights.append(f"📋 CMHC insurance of ${cmhc:,.0f} applies (down payment < 20%). This amount is added to your mortgage principal.")
    if down_payment_pct < 0.20:
        insights.append("💡 A 20%+ down payment eliminates CMHC insurance and reduces your total cost.")
    if req.credit_score < 650:
        insights.append("💡 Raising your credit score above 650 can meaningfully improve your offered rate.")
    if approval_prob >= 0.75:
        insights.append("✅ Strong approval profile. Shop multiple lenders — even 0.1% rate difference saves thousands over 25 years.")

    response = MortgageResponse(
        approval_probability=round(approval_prob, 4),
        approved=approval_prob >= 0.50,
        predicted_interest_rate=predicted_rate,
        monthly_payment=round(monthly, 2),
        total_payment=round(total_payment, 2),
        total_interest=round(total_interest, 2),
        cmhc_insurance=round(cmhc, 2),
        loan_amount=round(total_loan, 2),
        gds_ratio=round(gds, 4),
        tds_ratio=round(tds, 4),
        stress_test_rate=stress_test_rate,
        passes_stress_test=passes_stress_test,
        amortization_schedule=schedule,
        insights=insights,
    )

    await save_prediction(req.dict(), response.dict())
    return response


# ── History endpoint ──────────────────────────────────────────────────────────
@app.get("/history")
@limiter.limit("30/minute")
async def get_history(request: Request, limit: int = Query(20, ge=1, le=100)):
    if predictions_col is None:
        raise HTTPException(503, "MongoDB not configured. Add MONGODB_URI to .env")
    cursor = predictions_col.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return {"count": len(docs), "predictions": docs}


# ── Model status endpoint ─────────────────────────────────────────────────────
@app.get("/model/status")
async def model_status():
    from scheduler import _last_retrain_ts, RETRAIN_THRESHOLD, MAX_DOCS, TARGET_DOCS
    doc_count = await predictions_col.count_documents({}) if predictions_col is not None else 0
    new_since_retrain = (
        await predictions_col.count_documents({"timestamp": {"$gt": _last_retrain_ts}})
        if predictions_col is not None else 0
    )
    jobs = [
        {"id": job.id, "next_run": str(job.next_run_time)}
        for job in (_scheduler.get_jobs() if _scheduler else [])
    ]
    return {
        "total_predictions_stored": doc_count,
        "new_since_last_retrain":   new_since_retrain,
        "retrain_threshold":        RETRAIN_THRESHOLD,
        "last_retrain_utc":         _last_retrain_ts.isoformat(),
        "storage_max_docs":         MAX_DOCS,
        "storage_target_docs":      TARGET_DOCS,
        "scheduled_jobs":           jobs,
        "active_model": "hot-swapped" if app_state.get("approval_model") is not approval_model else "initial",
    }


# ── Health endpoint ───────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    mongo_ok = False
    if db_client:
        try:
            await db_client.admin.command("ping")
            mongo_ok = True
        except Exception:
            pass
    return {
        "status": "ok",
        "models_loaded": approval_model is not None,
        "mongodb_connected": mongo_ok,
    }
