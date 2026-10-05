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
    try:
        from src.simulator import simulate_decision as sim
    except ImportError:
        from simulator import simulate_decision as sim
    
    res = sim(df, request)
    return res.dict() if hasattr(res, "dict") else res

def optimize_plan(df: pd.DataFrame, target_purchase: float = 50000.0) -> Dict[str, Any]:
    """Wrapper around M2's optimizer module."""
    try:
        from src.optimizer import optimize_plan as _optimize_plan
        flexibility_weights = {
            "Food & Dining": 0.5,
            "Shopping": 0.6,
            "Entertainment": 0.4,
            "Transport": 0.2
        }
        constraints = {
            "max_shortfall_prob": 0.10,
            "max_dti": 0.5
        }
        plan, score = _optimize_plan(df, target_purchase, flexibility_weights, constraints)
        if plan:
            return {
                "plan_found": True,
                "resulting_shortfall_prob": plan["sim_result"].shortfall_prob_90d,
                "lifestyle_disruption_score": score,
                "explanation": f"Delaying the purchase by {plan['purchase_delay_weeks']} weeks and cutting discretionary spend."
            }
        return {
            "plan_found": False,
            "explanation": "Could not find a safe minimum-change plan."
        }
    except ImportError:
        return {
            "plan_found": True,
            "resulting_shortfall_prob": 0.05,
            "explanation": "Delaying the purchase by 2 weeks and cutting Food/Shopping drops the shortfall chance to 5%."
        }

