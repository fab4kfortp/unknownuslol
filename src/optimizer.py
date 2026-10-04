import numpy as np

def stub_simulator(plan, user_profile=None):
    """
    A stub for M1's Decision Simulator.
    Given a plan (cuts, delays, extra_savings), it returns:
    - shortfall_prob
    - p10_buffer
    - dti (debt-to-income)
    
    This is purely a mock function to allow the optimizer to run.
    """
    # A dummy logic: more cuts / delays -> lower shortfall prob
    base_shortfall = 0.40
    base_p10 = 10000
    base_dti = 0.45
    
    total_cut_pct = sum(plan.get("cuts", {}).values())
    delay_weeks = plan.get("purchase_delay_weeks", 0)
    extra_saving = plan.get("extra_monthly_saving", 0)
    
    improvement_factor = (total_cut_pct * 0.5) + (delay_weeks * 0.05) + (extra_saving / 50000.0)
    
    return {
        "shortfall_prob": max(0.0, base_shortfall - improvement_factor),
        "p10_buffer": base_p10 + (extra_saving * 2) + (delay_weeks * 500),
        "dti": max(0.1, base_dti - (total_cut_pct * 0.1))
    }

def optimize_plan(target_purchase, current_state, constraints, flexibility_weights):
    """
    Minimum-Change Optimizer using bounded search (Grid search over sensible bounds).
    
    Levers:
    - cut percentage per discretionary category (0 to 50%)
    - purchase delay in weeks (0 to 12)
    - extra monthly saving (0 to 20000)
    
    Objective: Minimise sum of (flexibility weight x cut) + penalty per week of delay.
    Constraints: shortfall_prob <= target_shortfall, p10_buffer >= min_buffer, dti <= max_dti.
    """
    categories = list(flexibility_weights.keys())
    
    best_plan = None
    best_score = float('inf')
    
    # Bounded grid search
    cut_options = [0.0, 0.1, 0.2, 0.3]
    delay_options = [0, 2, 4, 8]
    saving_options = [0, 5000, 10000]
    
    # Very naive search for demonstration
    for delay in delay_options:
        for saving in saving_options:
            # We assume a single uniform cut across all discretionary categories to keep grid small
            for cut in cut_options:
                plan = {
                    "cuts": {cat: cut for cat in categories},
                    "purchase_delay_weeks": delay,
                    "extra_monthly_saving": saving
                }
                
                # 1. Score lifestyle disruption (Objective)
                disruption = 0
                for cat in categories:
                    disruption += flexibility_weights[cat] * cut
                disruption += delay * 0.5  # arbitrary penalty per week
                
                # 2. Evaluate constraints using the simulator
                sim_result = stub_simulator(plan)
                
                if (sim_result["shortfall_prob"] <= constraints.get("max_shortfall_prob", 0.1) and
                    sim_result["p10_buffer"] >= constraints.get("min_p10_buffer", 0) and
                    sim_result["dti"] <= constraints.get("max_dti", 0.5)):
                    
                    if disruption < best_score:
                        best_score = disruption
                        best_plan = plan
                        best_plan["sim_result"] = sim_result
                        
    return best_plan, best_score

if __name__ == "__main__":
    flex_weights = {
        "Dining": 1.0,
        "Entertainment": 0.8,
        "Shopping": 1.5
    }
    constraints = {
        "max_shortfall_prob": 0.15,
        "min_p10_buffer": 15000,
        "max_dti": 0.40
    }
    
    plan, score = optimize_plan("Rs 90,000 laptop", {}, constraints, flex_weights)
    print("Best Plan:", plan)
    print("Disruption Score:", score)
