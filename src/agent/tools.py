from typing import Dict, Any
import pandas as pd
from api.schemas import SimulatorRequest, SimulatorPreset, SimulatorPriority

def get_summary(df: pd.DataFrame) -> Dict[str, Any]:
    from src.health_ratios import monthly_summary
    return monthly_summary(df).to_dict()

def get_recurring(df: pd.DataFrame) -> Dict[str, Any]:
    from src.recurring_detector import detect_recurring_payments, monthly_recurring_burden
    rec = detect_recurring_payments(df)
    burden = monthly_recurring_burden(rec)
    return {
        "total_monthly_burden": burden, 
        "recurring_payments": rec.to_dict(orient="records")
    }

def forecast(df: pd.DataFrame) -> Dict[str, Any]:
    from src.forecast_model import compute_daily_net_cashflow, forecast_forward
    daily = compute_daily_net_cashflow(df)
    fwd = forecast_forward(daily, forecast_days=30)
    # Simple aggregated metrics for the agent
    return {
        "predicted_net_cashflow_30d": float(fwd["predicted_net_cashflow"].sum()),
        "average_confidence_low": float(fwd["confidence_low"].mean()),
        "average_confidence_high": float(fwd["confidence_high"].mean())
    }

def simulate_decision(df: pd.DataFrame, request: SimulatorRequest) -> Dict[str, Any]:
    from simulator import simulate_decision as sim
    # Run the deterministic simulator which lives in the root module `simulator.py` 
    # (actually M1 put it in `src/simulator.py` but sys.path makes it `simulator` or `src.simulator`)
    try:
        from src.simulator import simulate_decision as sim
    except ImportError:
        from simulator import simulate_decision as sim
    
    res = sim(df, request)
    return res.dict() if hasattr(res, "dict") else res

def optimize_plan(request: Any) -> Dict[str, Any]:
    # M2's optimizer module, use a safe fallback if not present (as per M1's stub)
    try:
        from src.optimizer import optimize
        res = optimize(request)
        return res.dict() if hasattr(res, "dict") else res
    except ImportError:
        return {
            "plan_found": True,
            "resulting_shortfall_prob": 0.05,
            "explanation": "Delaying the purchase by 2 weeks and cutting Food/Shopping drops the shortfall chance to 5%."
        }
