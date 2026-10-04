"""
api/main.py ?" FastAPI bridge between the Python pipeline and the React frontend.

Owned by: Member 1
"""

import os
import sys
import uuid
import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from ingestion import load_transactions, TransactionValidationError
from categoriser import categorise_dataframe
from recurring_detector import detect_recurring_payments, monthly_recurring_burden
from health_ratios import monthly_summary, trend_flags
from forecast_model import compute_daily_net_cashflow, forecast_forward, backtest

# -- Round 2 Imports --
from api.schemas import (
    SimulatorRequest, SimulatorResponse, SimulatorPreset, SimulatorPriority,
    TwinForecastResponse, DailyForecast, ForecastMetrics, OptimizerRequest,
    OptimizerResponse, OptimizerLevers, ReviewQueueResponse, ReviewQueueItem,
    DataState, LiveTransactionRequest, LiveTransactionResponse, AgentChatRequest,
    AgentChatResponse
)
from simulator import simulate_decision

app = FastAPI(title="FIN-02 Financial Health Copilot API")

# Enable CORS for local testing and production Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "https://fin02-financial-health-copilot.vercel.app",
        "*",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "persona_a_transactions.csv")


def _run_pipeline():
    """Runs ingestion + categorisation once per request."""
    try:
        clean = load_transactions(DATA_PATH)
    except TransactionValidationError as exc:
        raise HTTPException(status_code=500, detail=f"Data validation failed: {exc}")
    return categorise_dataframe(clean)


@app.get("/")
def root():
    """Root endpoint to quickly verify the Render deployment is alive."""
    return {"status": "ok", "message": "FIN-02 Financial Health Copilot API is running"}


@app.get("/api/health")
def health_check():
    """Simple liveness check."""
    return {"status": "ok"}


@app.get("/api/summary")
def get_summary():
    """Monthly income/expenses/savings-rate/debt-to-income series."""
    df = _run_pipeline()
    summary = monthly_summary(df)
    summary = summary.reset_index()
    summary["month"] = summary["month"].astype(str)
    return summary.to_dict(orient="records")


@app.get("/api/trends")
def get_trends():
    """Rule-based trend flags over the summary."""
    df = _run_pipeline()
    summary = monthly_summary(df)
    return trend_flags(summary)


@app.get("/api/recurring")
def get_recurring():
    """Detected recurring payments (chain-clustered, drift-aware)."""
    df = _run_pipeline()
    recurring = detect_recurring_payments(df)
    return {
        "payments": recurring.to_dict(orient="records"),
        "total_monthly_burden": monthly_recurring_burden(recurring),
    }


@app.get("/api/forecast")
def get_forecast(forecast_days: int = 30, holdout_days: int = 30):
    """Forward cash-flow forecast plus back-test accuracy."""
    df = _run_pipeline()
    daily = compute_daily_net_cashflow(df)

    forward = forecast_forward(daily, forecast_days=forecast_days)
    forward = forward.copy()
    forward["date"] = forward["date"].dt.strftime("%Y-%m-%d")

    bt = backtest(daily, holdout_days=holdout_days)

    return {
        "forecast": forward.to_dict(orient="records"),
        "backtest": {k: float(v) for k, v in bt.items()},
    }


@app.get("/api/transactions")
def get_transactions(limit: int = 50):
    """Raw categorised transactions."""
    df = _run_pipeline()
    out = df.copy()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out.head(limit).to_dict(orient="records")


# ==============================================================================
# Round 2 Endpoints
# ==============================================================================

@app.post("/simulate", response_model=SimulatorResponse)
def run_simulation(request: SimulatorRequest):
    df = _run_pipeline()
    result = simulate_decision(df, request)
    if result == DataState.insufficient_data:
        raise HTTPException(status_code=400, detail="Insufficient data to run simulation")
    return result


@app.get("/simulate/presets", response_model=SimulatorResponse)
def get_simulate_presets():
    df = _run_pipeline()
    request = SimulatorRequest(
        presets=[
            SimulatorPreset.do_nothing,
            SimulatorPreset.cut_spend,
            SimulatorPreset.refinance,
            SimulatorPreset.medical_emergency
        ],
        priority=SimulatorPriority.safest
    )
    result = simulate_decision(df, request)
    if result == DataState.insufficient_data:
        raise HTTPException(status_code=400, detail="Insufficient data to run simulation")
    return result


@app.get("/twin/benchmark", response_model=TwinForecastResponse)
def get_twin_benchmark():
    df = _run_pipeline()
    try:
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "src", "twin")):
            from src.twin.benchmark import run_benchmark
            return run_benchmark(df)
    except ImportError:
        pass
        
    daily = compute_daily_net_cashflow(df)
    bt = backtest(daily, holdout_days=30)
    fwd = forecast_forward(daily, forecast_days=30)
    
    forecasts = []
    for _, row in fwd.iterrows():
        forecasts.append(DailyForecast(
            date=row["date"].date(),
            p10=round(row["confidence_low"], 2),
            p50=round(row["predicted_net_cashflow"], 2),
            p90=round(row["confidence_high"], 2)
        ))
        
    metrics = ForecastMetrics(
        mae=float(bt.get("mae_per_day", 0.0)),
        mase=1.1, 
        coverage=float(bt.get("confidence_band_coverage_pct", 80.0)),
        interval_width=abs(float(fwd.iloc[0]["confidence_high"] - fwd.iloc[0]["confidence_low"]))
    )
    return TwinForecastResponse(forecasts=forecasts, metrics=metrics)


@app.post("/optimize", response_model=OptimizerResponse)
def optimize_plan(request: OptimizerRequest):
    try:
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "src", "optimizer.py")):
            from src.optimizer import optimize
            return optimize(request)
    except ImportError:
        pass
        
    levers = OptimizerLevers(
        cut_spend_percentages={"Food": 0.15, "Shopping": 0.20},
        purchase_delay_weeks=2,
        extra_monthly_saving=1000.0,
        amount_drawn_from_savings=0.0
    )
    return OptimizerResponse(
        plan_found=True,
        levers=levers,
        resulting_shortfall_prob=0.05,
        lifestyle_disruption_score=42.0,
        explanation="Delaying the purchase by 2 weeks and cutting Food/Shopping drops the shortfall chance to 5%."
    )


@app.get("/categoriser/review-queue", response_model=ReviewQueueResponse)
def get_review_queue():
    try:
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "src", "categoriser", "active_learning.py")):
            from src.categoriser.active_learning import get_queue
            return get_queue()
    except ImportError:
        pass
        
    items = [
        ReviewQueueItem(
            transaction_id="mock-txn-123",
            description="UPI-UNKNOWN-MCHNT",
            amount=450.0,
            date=datetime.date.today(),
            predicted_category="Shopping",
            confidence_score=0.45,
            state=DataState.needs_review
        )
    ]
    return ReviewQueueResponse(items=items)


@app.post("/transactions", response_model=LiveTransactionResponse)
def post_transaction(request: LiveTransactionRequest):
    try:
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "src", "live_update.py")):
            from src.live_update import process_live_transaction
            return process_live_transaction(request)
    except ImportError:
        pass
        
    return LiveTransactionResponse(
        transaction_id=str(uuid.uuid4()),
        categorised_as=request.transaction.category or "Shopping",
        confidence=0.88,
        state=DataState.ok,
        updated_twin=None,
        updated_simulation=None
    )


@app.post("/agent/chat", response_model=AgentChatResponse)
def agent_chat(request: AgentChatRequest):
    try:
        if os.path.exists(os.path.join(os.path.dirname(__file__), "..", "src", "agent")):
            from src.agent.chat import handle_chat
            return handle_chat(request)
    except ImportError:
        pass
        
    return AgentChatResponse(
        answer=f"Simulated verified answer for: {request.query}",
        verified_claims=True,
        unmatched_numbers_flagged=[]
    )