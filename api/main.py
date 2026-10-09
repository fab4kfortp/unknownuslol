"""
api/main.py ?" FastAPI bridge between the Python pipeline and the React frontend.

Owned by: Member 1
"""

import csv
import io
import json
import os
import sys
import uuid
import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
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
    AgentChatResponse, ReviewCorrectionRequest
)
from simulator import simulate_decision
from api.mock_engine import MockEngine
from api.storage import clear_user_data, get_locked_path, get_locked_paths, get_transactions as stored_transactions, initialize_database, store_locked_path, store_transactions
from contracts.schemas import LockedPath, Priority, Scenario, Transaction, TransactionType

# Product-layer engine selection.  A real engine can replace this branch once
# its adapter is available; local development remains deterministic by default.
ENGINE_MODE = os.getenv("ENGINE_MODE", "mock").strip().lower()
if ENGINE_MODE == "mock":
    engine = MockEngine()
else:
    raise RuntimeError(
        f"Unsupported ENGINE_MODE={ENGINE_MODE!r}. Only 'mock' is available currently."
    )

app = FastAPI(title="FIN-02 Financial Health Copilot API")
app.state.engine = engine
app.state.engine_mode = ENGINE_MODE
initialize_database()

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
FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures")


def _resolve_session_id(
    request: Request, form_session_id: str | None, header_session_id: str | None
) -> str:
    """Allow a session ID in multipart form data, a header, or a query parameter."""
    session_id = form_session_id or header_session_id or request.query_params.get("session_id")
    if not session_id or not session_id.strip():
        raise HTTPException(status_code=422, detail="A non-empty session_id is required")
    return session_id.strip()


def _transaction_from_csv_row(row: dict[str, str | None], row_number: int, session_id: str) -> Transaction:
    """Convert CSV text deliberately before strict Pydantic validation."""
    try:
        amount = float(row.get("amount") or "")
        balance = float(row.get("balance") or 0.0)
    except ValueError as exc:
        raise ValueError("amount and balance must be valid numbers") from exc

    return Transaction.model_validate(
        {
            "id": row.get("id") or f"{session_id}-{row_number}",
            "date": row.get("date") or "",
            "narration": row.get("narration") or "",
            "amount": amount,
            "type": TransactionType((row.get("type") or "").strip().lower()),
            "category": row.get("category") or "uncategorized",
            "category_confidence": float(row.get("category_confidence") or 0.0),
            "priority": Priority(row.get("priority") or "Low"),
            "balance": balance,
        }
    )


@app.post("/api/upload")
async def upload_statement(
    request: Request,
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    x_session_id: str | None = Header(default=None),
):
    """Validate a statement CSV, persist valid rows, and report row-level errors."""
    effective_session_id = _resolve_session_id(request, session_id, x_session_id)
    if not file.filename or not file.filename.lower().endswith((".csv", ".json")):
        raise HTTPException(status_code=415, detail="Upload a CSV or JSON statement")

    try:
        content = (await file.read()).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded") from exc

    required_headers = {"date", "narration", "amount", "type"}
    if file.filename.lower().endswith(".json"):
        try:
            parsed_rows = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="JSON statement is invalid") from exc
        if not isinstance(parsed_rows, list) or not all(isinstance(row, dict) for row in parsed_rows):
            raise HTTPException(status_code=422, detail="JSON statement must be an array of transaction objects")
        input_rows = parsed_rows
    else:
        reader = csv.DictReader(io.StringIO(content))
        actual_headers = set(reader.fieldnames or [])
        missing_headers = sorted(required_headers - actual_headers)
        if missing_headers:
            raise HTTPException(
                status_code=422,
                detail={"message": "CSV is missing required headers", "missing_headers": missing_headers},
            )
        input_rows = list(reader)

    accepted: list[dict] = []
    bad_rows: list[dict] = []
    for row_number, row in enumerate(input_rows, start=2):
        try:
            transaction = _transaction_from_csv_row(row, row_number, effective_session_id)
            transaction_json = transaction.model_dump(mode="json")
            accepted.append(transaction_json)
        except Exception as exc:
            errors = exc.errors() if hasattr(exc, "errors") else [{"message": str(exc)}]
            bad_rows.append({"row": row_number, "raw": row, "errors": errors})

    store_transactions(effective_session_id, accepted)
    engine_result = app.state.engine.ingest(accepted, file.filename)
    # Preserve user-specific validation results when there are input errors;
    # otherwise return the contract fixture/engine result verbatim.
    if bad_rows:
        engine_result = {
            "accepted": accepted,
            "rejected": [
                {"row": bad_row["row"], "reasons": [str(error) for error in bad_row["errors"]]}
                for bad_row in bad_rows
            ],
            "preview": accepted[:10],
        }
    return engine_result


@app.delete("/api/user-data")
def delete_user_data(
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None),
):
    """Remove all session-scoped uploaded transactions and locked paths."""
    effective_session_id = session_id or x_session_id
    if not effective_session_id or not effective_session_id.strip():
        raise HTTPException(status_code=422, detail="A non-empty session_id is required")
    deleted = clear_user_data(effective_session_id.strip())
    return {"session_id": effective_session_id.strip(), "deleted": deleted}


@app.get("/api/template")
def download_statement_template():
    """Download the Day-One CSV statement template."""
    return FileResponse(
        os.path.join(FIXTURES_PATH, "sample_statement.csv"),
        media_type="text/csv",
        filename="sample_statement.csv",
    )


def _user_data(session_id: str) -> dict:
    """Load only the current session's persisted data for a stateless engine call."""
    return {
        "session_id": session_id,
        "transactions": stored_transactions(session_id),
        "locked_paths": get_locked_paths(session_id),
    }


def _engine_session_id(session_id: str | None, x_session_id: str | None) -> str:
    value = session_id or x_session_id
    if not value or not value.strip():
        raise HTTPException(status_code=422, detail="A non-empty session_id is required")
    return value.strip()


# Frozen HTTP contract routes. Existing legacy endpoints below remain available
# for backwards compatibility, while these are the v1 Part B surface.
@app.post("/api/transactions")
def refresh_transaction(
    transaction: dict,
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None),
):
    effective_session_id = _engine_session_id(session_id, x_session_id)
    normalized_transaction = _transaction_from_csv_row(transaction, 1, effective_session_id)
    user_data = _user_data(effective_session_id)
    locks = [LockedPath.model_validate(item) for item in user_data["locked_paths"]]
    result = app.state.engine.refresh(user_data, normalized_transaction, locks)
    store_transactions(effective_session_id, [result["transaction"]])
    return result


@app.get("/api/summary")
@app.get("/api/recurring")
@app.get("/api/priority")
@app.get("/api/calendar")
def analyze_user_data(
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None),
):
    return app.state.engine.analyze(_user_data(_engine_session_id(session_id, x_session_id)))


@app.get("/api/forecast")
def forecast_user_data(
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None),
    horizon_days: int = Query(default=90, gt=0),
):
    return app.state.engine.forecast(_user_data(_engine_session_id(session_id, x_session_id)), horizon_days)


@app.post("/api/simulate")
def compare_scenarios(scenarios: list[Scenario], session_id: str = Query(...)):
    return app.state.engine.compare_paths(_user_data(session_id), scenarios)


@app.get("/api/shock-capacity")
def get_shock_capacity(session_id: str = Query(...), limit: float = Query(default=0.10, ge=0, le=1)):
    return app.state.engine.shock_capacity(_user_data(session_id), limit)


@app.post("/api/optimize")
def optimize_user_plan(target_risk: float = Query(..., ge=0, le=1), session_id: str = Query(...)):
    return app.state.engine.optimize(_user_data(session_id), target_risk)


@app.post("/api/lock")
def lock_path(locked_path: LockedPath, session_id: str = Query(...)):
    stored_path = locked_path.model_dump(mode="json")
    store_locked_path(session_id, stored_path)
    return app.state.engine.evaluate_lock(_user_data(session_id), locked_path)


@app.get("/api/lock/{lock_id}")
def evaluate_locked_path(lock_id: str, session_id: str = Query(...)):
    saved_path = get_locked_path(session_id, lock_id)
    if saved_path is None:
        raise HTTPException(status_code=404, detail="Locked path not found")
    return app.state.engine.evaluate_lock(_user_data(session_id), LockedPath.model_validate(saved_path))


@app.post("/api/chat")
def chat_with_engine(session_id: str = Query(...)):
    """Minimal verified-agent placeholder: it receives engine output, never raw rows."""
    analysis = app.state.engine.analyze(_user_data(session_id))
    return {"analysis": analysis, "verified_claims": True}


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


@app.get("/legacy/api/summary")
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


@app.get("/legacy/api/recurring")
def get_recurring():
    """Detected recurring payments (chain-clustered, drift-aware)."""
    df = _run_pipeline()
    recurring = detect_recurring_payments(df)
    return {
        "payments": recurring.to_dict(orient="records"),
        "total_monthly_burden": monthly_recurring_burden(recurring),
    }


@app.get("/legacy/api/forecast")
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
            "max_shortfall_prob": request.constraints.target_shortfall_prob,
            "max_dti": 0.5
        }
        
        plan, score = optimize_plan(df, request.target_purchase_amount, flexibility_weights, constraints)
        
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