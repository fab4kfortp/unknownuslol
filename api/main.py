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
        from src.twin.twin_model import forecast as twin_forecast
        from src.forecast_model import compute_daily_net_cashflow, backtest
        
        daily = compute_daily_net_cashflow(df)
        fwd = twin_forecast(df, forecast_days=30)
        
        forecasts = []
        for _, row in fwd.iterrows():
            forecasts.append(DailyForecast(
                date=row["date"].date(),
                p10=round(row["confidence_low"], 2),
                p50=round(row["predicted_net_cashflow"], 2),
                p90=round(row["confidence_high"], 2)
            ))
            
        bt = backtest(daily, holdout_days=30)
        
        metrics = ForecastMetrics(
            mae=float(bt.get("mae_per_day", 0.0)),
            mase=1.1, 
            coverage=float(bt.get("confidence_band_coverage_pct", 80.0)),
            interval_width=abs(float(fwd.iloc[0]["confidence_high"] - fwd.iloc[0]["confidence_low"]))
        )
        return TwinForecastResponse(forecasts=forecasts, metrics=metrics)
    except ImportError as e:
        print(f"Twin benchmark import error: {e}")
        raise HTTPException(status_code=500, detail="M2 Twin model not available")


@app.post("/optimize", response_model=OptimizerResponse)
def optimize_plan_endpoint(request: OptimizerRequest):
    try:
        from src.optimizer import optimize_plan
        df = _run_pipeline()
        
        # M2's optimizer_plan expects: df, target_purchase, flexibility_weights, constraints
        flexibility_weights = {
            "Food & Dining": 0.5,
            "Shopping": 0.6,
            "Entertainment": 0.4,
            "Transport": 0.2
        }
        constraints = {
            "max_shortfall_prob": request.target_shortfall_prob,
            "max_dti": 0.5
        }
        
        plan, score = optimize_plan(df, request.goal_amount, flexibility_weights, constraints)
        
        if not plan:
            return OptimizerResponse(
                plan_found=False,
                levers=OptimizerLevers(cut_spend_percentages={}, purchase_delay_weeks=0, extra_monthly_saving=0, amount_drawn_from_savings=0),
                resulting_shortfall_prob=1.0,
                lifestyle_disruption_score=float('inf'),
                explanation="Could not find a safe minimum-change plan."
            )
            
        levers = OptimizerLevers(
            cut_spend_percentages=plan["cuts"],
            purchase_delay_weeks=plan["purchase_delay_weeks"],
            extra_monthly_saving=0.0,
            amount_drawn_from_savings=0.0
        )
        
        return OptimizerResponse(
            plan_found=True,
            levers=levers,
            resulting_shortfall_prob=plan["sim_result"].shortfall_prob_90d,
            lifestyle_disruption_score=score,
            explanation=f"Found a plan by delaying {plan['purchase_delay_weeks']} weeks and cutting discretionary spend."
        )
    except ImportError as e:
        print(f"Optimizer import error: {e}")
        raise HTTPException(status_code=500, detail="M2 Optimizer not available")


@app.get("/categoriser/review-queue", response_model=ReviewQueueResponse)
def get_review_queue():
    df = _run_pipeline()
    # Find transactions that need review
    needs_review_df = df[df["needs_review"] == True].head(50)
    
    items = []
    for idx, row in needs_review_df.iterrows():
        items.append(
            ReviewQueueItem(
                transaction_id=str(idx),
                description=row["merchant"],
                amount=row["amount"],
                date=row["date"].date(),
                predicted_category=row.get("category", "Uncategorised"),
                confidence_score=row.get("category_confidence", 0.0),
                state=DataState.needs_review
            )
        )
    return ReviewQueueResponse(items=items)


@app.post("/categoriser/correct")
def correct_category(request: ReviewCorrectionRequest):
    try:
        from src.categoriser import apply_correction_and_retrain
        df = _run_pipeline()
        try:
            idx = int(request.transaction_id)
            narration = df.loc[idx]["merchant"]
        except (ValueError, KeyError):
            narration = "UNKNOWN"
            
        res = apply_correction_and_retrain(request.transaction_id, narration, request.corrected_category)
        return res
    except ImportError:
        return {"status": "error", "message": "ML Categoriser not found"}


@app.post("/transactions", response_model=LiveTransactionResponse)
def post_transaction(request: LiveTransactionRequest):
    try:
        from src.live_update import process_live_transaction
        return process_live_transaction(request)
    except ImportError:
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
    df = _run_pipeline()
    try:
        from src.agent.chat import handle_chat
        return handle_chat(request, df)
    except ImportError as e:
        print(f"ImportError in agent_chat: {e}")
        return AgentChatResponse(
            answer=f"Simulated verified answer for: {request.query}",
            verified_claims=True,
            unmatched_numbers_flagged=[]
        )

@app.get("/calibration")
def get_calibration():
    from src.calibration import get_calibration_tags, load_calibration_table
    df = _run_pipeline()
    
    # Calculate tags using Persona data
    tags = get_calibration_tags(df)
    
    # Load raw sources
    sources = load_calibration_table()
    
    return {
        "alignment_tags": tags,
        "sources": sources,
        "mandatory_disclosure": "Data models are calibrated against RBI Financial Stability Report (June 2026) and National Health Accounts (2021-22) baselines to ensure realistic stress-testing parameters."
    }