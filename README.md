# MortgageIQ 🍁

> Canada's intelligent homebuying advisor — instant mortgage assessment powered by AI.

## Features
- **Approval probability** — trained on 20,000 CMHC-calibrated samples
- **Interest rate forecast** — personalised to your credit score, down payment & employment type
- **GDS / TDS ratio check** — Canadian 39% / 44% limits
- **CMHC insurance calculation** — automatic based on down payment %
- **OSFI B-20 stress test** — qualifies you at rate + 2% or 5.25%
- **Full amortization schedule** — year-by-year breakdown with charts
- **Auto-retraining** — models retrain on real user data stored in MongoDB
- **Auto-purge** — oldest records deleted automatically when storage approaches Atlas M0 limit

## Stack
| Layer | Technology |
|---|---|
| Frontend | React 18, Framer Motion, Recharts |
| Backend | Python, FastAPI, APScheduler |
| ML | scikit-learn (Random Forest + Gradient Boosting) |
| Database | MongoDB Atlas (free M0 tier) |

## Quick Start

### 1. Backend
```bash
cd backend
pip install -r requirements.txt

# Train the ML model
python model/train_model.py

# Add your MongoDB connection string
cp .env.example .env
# Edit .env with your MONGODB_URI

# Start the API
uvicorn main:app --reload --port 8000
```

### 2. Frontend
```bash
cd frontend
npm install
npm start
```

App runs at `http://localhost:3000` · API at `http://localhost:8000`

## Environment Variables (`backend/.env`)
```
MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/...
DB_NAME=mortgage_predictor
MAX_DOCS=150000       # purge trigger (Atlas M0 ≈ 512MB)
TARGET_DOCS=100000    # keep this many after purge
RETRAIN_THRESHOLD=500 # new records before retraining
```

## API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| POST | `/predict` | Run mortgage assessment |
| GET | `/history?limit=20` | Recent predictions from MongoDB |
| GET | `/model/status` | Scheduler state & training stats |
| GET | `/health` | Server + DB health check |

## Disclaimer
Not financial advice. For informational purposes only.
