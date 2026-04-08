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
from scheduler import start_scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO)

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

# ── MongoDB setup ─────────────────────────────────────────────────────────────
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "mortgage_predictor")

db_client: AsyncIOMotorClient | None = None
predictions_col = None
_scheduler = None

# Mutable state dict — scheduler swaps models in here without restart
app_state: dict = {}


@app.on_event("startup")
async def startup_db():
    global db_client, predictions_col, _scheduler
    if MONGODB_URI:
        db_client = AsyncIOMotorClient(MONGODB_URI)
        db = db_client[DB_NAME]
        predictions_col = db["predictions"]
        await predictions_col.create_index("timestamp")
        print(f"✅ MongoDB connected → {DB_NAME}.predictions")

        # Pass mutable app_state so scheduler can hot-swap models
        app_state["approval_model"] = approval_model
        app_state["rate_model"]     = rate_model
        app_state["scaler"]         = scaler
        _scheduler = start_scheduler(predictions_col, app_state)
    else:
        print("⚠️  MONGODB_URI not set — predictions will not be stored. Add .env to enable.")


@app.on_event("shutdown")
async def shutdown_db():
    if _scheduler:
        _scheduler.shutdown(wait=False)
    if db_client:
        db_client.close()


async def save_prediction(input_data: dict, result_data: dict):
    """Persist input + result to MongoDB. Silently skips if DB not configured."""
    if predictions_col is None:
        return
    try:
        doc = {
            "timestamp": datetime.now(timezone.utc),
            "input": input_data,
            "result": {
                "approval_probability": result_data["approval_probability"],
                "approved": result_data["approved"],
                "predicted_interest_rate": result_data["predicted_interest_rate"],
                "monthly_payment": result_data["monthly_payment"],
                "total_payment": result_data["total_payment"],
                "total_interest": result_data["total_interest"],
                "cmhc_insurance": result_data["cmhc_insurance"],
                "loan_amount": result_data["loan_amount"],
                "gds_ratio": result_data["gds_ratio"],
                "tds_ratio": result_data["tds_ratio"],
                "passes_stress_test": result_data["passes_stress_test"],
            },
        }
        await predictions_col.insert_one(doc)
    except Exception as e:
        print(f"⚠️  MongoDB write failed: {e}")

# ── Load models ───────────────────────────────────────────────────────────────
MODEL_DIR = os.path.join(os.path.dirname(__file__), "model")

try:
    approval_model = joblib.load(os.path.join(MODEL_DIR, "approval_model.pkl"))
    rate_model = joblib.load(os.path.join(MODEL_DIR, "rate_model.pkl"))
    scaler = joblib.load(os.path.join(MODEL_DIR, "scaler.pkl"))
    features = joblib.load(os.path.join(MODEL_DIR, "features.pkl"))
    print("✅ Models loaded successfully")
except FileNotFoundError:
    print("⚠️  Models not found. Run model/train_model.py first.")
    approval_model = rate_model = scaler = features = None

# ── Province encoding ─────────────────────────────────────────────────────────
PROVINCE_MAP = {
    "ON": 0, "BC": 1, "AB": 2, "QC": 3, "MB": 4,
    "SK": 5, "NS": 6, "NB": 7, "NL": 8, "PE": 9,
}

EMPLOYMENT_MAP = {"salaried": 0, "self_employed": 1, "contract": 2}
PROPERTY_TYPE_MAP = {"condo": 0, "house": 1, "townhouse": 2}


# ── Request/Response schemas ──────────────────────────────────────────────────
class MortgageRequest(BaseModel):
    annual_income: float = Field(..., gt=0, description="Annual gross income in CAD")
    credit_score: int = Field(..., ge=300, le=900, description="Credit score (300-900)")
    property_value: float = Field(..., gt=0, description="Property purchase price in CAD")
    down_payment: float = Field(..., gt=0, description="Down payment amount in CAD")
    existing_monthly_debt: float = Field(0, ge=0, description="Existing monthly debt payments")
    employment_type: str = Field(..., description="salaried | self_employed | contract")
    province: str = Field(..., description="Canadian province code (e.g. ON, BC)")
    amortization: int = Field(25, description="Amortization period in years (15-30)")
    property_type: str = Field("house", description="condo | house | townhouse")

    @validator("province")
    def province_valid(cls, v):
        if v.upper() not in PROVINCE_MAP:
            raise ValueError(f"Province must be one of {list(PROVINCE_MAP.keys())}")
        return v.upper()

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
        if v not in [15, 20, 25, 30]:
            raise ValueError("Amortization must be 15, 20, 25, or 30 years")
        return v


class AmortizationRow(BaseModel):
    year: int
    principal_paid: float
    interest_paid: float
    remaining_balance: float


class MortgageResponse(BaseModel):
    approval_probability: float
    approved: bool
    predicted_interest_rate: float
    monthly_payment: float
    total_payment: float
    total_interest: float
    cmhc_insurance: float
    loan_amount: float
    gds_ratio: float
    tds_ratio: float
    stress_test_rate: float
    passes_stress_test: bool
    amortization_schedule: list[AmortizationRow]
    insights: list[str]


# ── Helper: CMHC insurance ────────────────────────────────────────────────────
def calculate_cmhc(property_value: float, down_payment: float) -> float:
    dp_pct = down_payment / property_value
    if dp_pct >= 0.20:
        return 0.0
    if property_value > 1_500_000:
        return 0.0  # Not eligible for CMHC over $1.5M
    if dp_pct < 0.10:
        rate = 0.0400
    elif dp_pct < 0.15:
        rate = 0.0310
    else:
        rate = 0.0280
    insured_amount = property_value - down_payment
    return round(insured_amount * rate, 2)


# ── Helper: monthly mortgage payment ─────────────────────────────────────────
def monthly_payment_calc(principal: float, annual_rate_pct: float, years: int) -> float:
    r = (annual_rate_pct / 100) / 12
    n = years * 12
    if r == 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)


# ── Helper: amortization schedule (yearly summary) ───────────────────────────
def build_amortization_schedule(principal: float, annual_rate_pct: float, years: int):
    r = (annual_rate_pct / 100) / 12
    balance = principal
    schedule = []
    for year in range(1, years + 1):
        year_interest = 0.0
        year_principal = 0.0
        for _ in range(12):
            interest = balance * r
            payment = monthly_payment_calc(principal, annual_rate_pct, years)
            prin = payment - interest
            year_interest += interest
            year_principal += prin
            balance -= prin
            balance = max(balance, 0)
        schedule.append(AmortizationRow(
            year=year,
            principal_paid=round(year_principal, 2),
            interest_paid=round(year_interest, 2),
            remaining_balance=round(max(balance, 0), 2),
        ))
    return schedule


# ── Prediction endpoint ───────────────────────────────────────────────────────
@app.post("/predict", response_model=MortgageResponse)
@limiter.limit("10/minute")
async def predict_mortgage(request: Request, req: MortgageRequest):
    if approval_model is None:
        raise HTTPException(503, "Models not loaded. Run train_model.py first.")

    # Derived ratios
    monthly_income = req.annual_income / 12
    down_payment_pct = req.down_payment / req.property_value
    loan_amount = req.property_value - req.down_payment
    cmhc = calculate_cmhc(req.property_value, req.down_payment)
    total_loan = loan_amount + cmhc

    # Rough GDS/TDS using 5.25% stress test rate for ratio calculation
    stress_rate = 5.25
    est_payment = monthly_payment_calc(total_loan, stress_rate, req.amortization)
    property_tax_heat = req.property_value * 0.015 / 12  # ~1.5% annual property tax
    gds = (est_payment + property_tax_heat) / monthly_income
    tds = gds + req.existing_monthly_debt / monthly_income

    # Encode features
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

    # Use hot-swapped models if available, else fall back to initial load
    _approval_model = app_state.get("approval_model", approval_model)
    _rate_model     = app_state.get("rate_model", rate_model)
    _scaler         = app_state.get("scaler", scaler)

    X_scaled = _scaler.transform(feature_vector)

    approval_prob = float(_approval_model.predict_proba(X_scaled)[0][1])
    predicted_rate = float(_rate_model.predict(X_scaled)[0])
    predicted_rate = round(max(2.5, min(9.5, predicted_rate)), 2)

    # Actual payment at predicted rate
    monthly = monthly_payment_calc(total_loan, predicted_rate, req.amortization)
    total_payment = monthly * req.amortization * 12
    total_interest = total_payment - total_loan

    # Stress test: qualify at max(predicted_rate + 2%, 5.25%)
    stress_test_rate = max(predicted_rate + 2.0, 5.25)
    stress_payment = monthly_payment_calc(total_loan, stress_test_rate, req.amortization)
    stress_gds = (stress_payment + property_tax_heat) / monthly_income
    stress_tds = stress_gds + req.existing_monthly_debt / monthly_income
    passes_stress_test = stress_gds <= 0.39 and stress_tds <= 0.44

    # Build schedule
    schedule = build_amortization_schedule(total_loan, predicted_rate, req.amortization)

    # Insights
    insights = []
    if approval_prob < 0.5:
        insights.append("⚠️ Low approval probability. Consider a larger down payment or improving credit score.")
    if gds > 0.39:
        insights.append(f"⚠️ GDS ratio ({gds:.1%}) exceeds Canadian standard of 39%. Reduce property value or increase income.")
    if tds > 0.44:
        insights.append(f"⚠️ TDS ratio ({tds:.1%}) exceeds Canadian standard of 44%. Pay down existing debts first.")
    if not passes_stress_test:
        insights.append("⚠️ Does not pass the Canadian mortgage stress test (OSFI B-20 guideline).")
    if cmhc > 0:
        insights.append(f"📋 CMHC insurance of ${cmhc:,.0f} applies (down payment < 20%). This is added to your mortgage.")
    if down_payment_pct < 0.20:
        insights.append("💡 A 20%+ down payment eliminates CMHC insurance and lowers monthly costs.")
    if req.credit_score < 650:
        insights.append("💡 Raising your credit score above 650 can significantly improve your rate.")
    if approval_prob >= 0.75:
        insights.append("✅ Strong approval profile. Shop multiple lenders for the best rate.")

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
        stress_test_rate=round(stress_test_rate, 2),
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
    """Return the most recent predictions stored in MongoDB."""
    if predictions_col is None:
        raise HTTPException(503, "MongoDB not configured. Add MONGODB_URI to .env")
    cursor = predictions_col.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return {"count": len(docs), "predictions": docs}


@app.get("/model/status")
async def model_status():
    """Shows model version, training data size, and next scheduler runs."""
    from scheduler import _last_retrain_ts, RETRAIN_THRESHOLD, MAX_DOCS, TARGET_DOCS
    doc_count = await predictions_col.count_documents({}) if predictions_col is not None else 0
    new_since_retrain = (
        await predictions_col.count_documents({"timestamp": {"$gt": _last_retrain_ts}})
        if predictions_col is not None else 0
    )
    jobs = []
    if _scheduler:
        for job in _scheduler.get_jobs():
            jobs.append({"id": job.id, "next_run": str(job.next_run_time)})

    return {
        "total_predictions_stored": doc_count,
        "new_since_last_retrain":   new_since_retrain,
        "retrain_threshold":        RETRAIN_THRESHOLD,
        "last_retrain_utc":         _last_retrain_ts.isoformat(),
        "storage_max_docs":         MAX_DOCS,
        "storage_target_docs":      TARGET_DOCS,
        "scheduled_jobs":           jobs,
        "active_model":             "hot-swapped" if app_state.get("approval_model") is not approval_model else "initial",
    }


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
