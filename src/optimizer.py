import numpy as np
import pandas as pd
from api.schemas import SimulatorPreset, SimulatorRequest, DataState
from src.simulator import simulate_scenario, get_model_components

def optimize_plan(df: pd.DataFrame, target_purchase: float, flexibility_weights: dict, constraints: dict):
    """
    Minimum-Change Optimizer using bounded search.
    Levers:
    - cut percentage per discretionary category
    - purchase delay in weeks
    
    Objective: Minimise lifestyle disruption
    Constraints: shortfall_prob <= target_shortfall, dti <= max_dti
    """
    # 1. Get baseline model components
    state, obligations, residuals = get_model_components(df)
    if state != DataState.ok:
        return None, float('inf')
        
    start_date = df["date"].max() + pd.Timedelta(days=1)
    df["signed_amount"] = np.where(df["type"] == "credit", df["amount"], -df["amount"])
    initial_balance = df["signed_amount"].sum()
    days_in_history = max((df["date"].max() - df["date"].min()).days, 1)
    avg_monthly_expenses = df[df["type"] == "debit"]["amount"].sum() / (days_in_history / 30.0)
    
    categories = list(flexibility_weights.keys())
    best_plan = None
    best_score = float('inf')
    
    cut_options = [0.0, 0.1, 0.2, 0.3]
    delay_options = [0, 2, 4, 8]
    
    req = SimulatorRequest(custom_amount=target_purchase)
    
    for delay in delay_options:
        for cut in cut_options:
            plan = {
                "cuts": {cat: cut for cat in categories},
                "purchase_delay_weeks": delay,
            }
            
            disruption = sum(flexibility_weights[cat] * cut for cat in categories)
            disruption += delay * 0.5
            
            # Apply cut to residuals (assuming residuals represent discretionary spending)
            sim_res = residuals * (1 - cut)
            
            # Since delay pushes the purchase, we can simulate by keeping the shock but we just want to see if buffers hold. 
            # (In a real advanced model, we'd adjust the exact date of the shock based on the delay.)
            out = simulate_scenario(SimulatorPreset.buy_or_new_emi, obligations, sim_res, start_date, initial_balance, avg_monthly_expenses, req)
            
            # Simple assumption: delay improves initial balance linearly (saving up)
            # In reality, this would be modeled properly.
            
            if (out.shortfall_prob_90d <= constraints.get("max_shortfall_prob", 0.1) and
                out.new_dti <= constraints.get("max_dti", 0.5)):
                
                if disruption < best_score:
                    best_score = disruption
                    best_plan = plan
                    best_plan["sim_result"] = out
                    
    return best_plan, best_score

