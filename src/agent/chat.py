import os
from typing import Dict, Any
import pandas as pd

from api.schemas import AgentChatRequest, AgentChatResponse, SimulatorRequest, SimulatorPreset, SimulatorPriority
from src.agent.tools import get_summary, get_recurring, forecast, simulate_decision, optimize_plan
from src.agent.verifier import verify_claims

def handle_chat(request: AgentChatRequest, df: pd.DataFrame) -> AgentChatResponse:
    query = request.query.lower()
    
    tool_outputs = {}
    draft_answer = ""
    
    # Deterministic fallback logic to route queries to tools (used for demos when no LLM key is present)
    if "recurring" in query or "subscription" in query:
        out = get_recurring(df)
        tool_outputs["recurring"] = out
        val = out.get('total_monthly_burden', 0)
        draft_answer = f"Your total monthly recurring burden is Rs {val:.2f}."
    elif "forecast" in query or "next month" in query:
        out = forecast(df)
        tool_outputs["forecast"] = out
        val = out.get('predicted_net_cashflow_30d', 0)
        draft_answer = f"Your predicted net cashflow for the next 30 days is Rs {val:.2f}."
    elif "simulate" in query or "decision" in query or "cut spend" in query:
        req = SimulatorRequest(presets=[SimulatorPreset.do_nothing, SimulatorPreset.cut_spend], priority=SimulatorPriority.safest)
        out = simulate_decision(df, req)
        tool_outputs["simulate"] = out
        if isinstance(out, dict) and "paths" in out and len(out["paths"]) > 0:
            draft_answer = out["paths"][0].get("one_line_reason", "I simulated the decision based on your request.")
        else:
            draft_answer = "I simulated the decision based on your request."
    else:
        out = get_summary(df)
        tool_outputs["summary"] = out
        draft_answer = "Based on the summary, your overall health ratios are computed. Your data has been processed safely."

    # External LLM hook
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        # In a real implementation we would call the LLM here and pass the tool outputs.
        # It would formulate the draft_answer.
        pass

    # Verification Step: The LLM's draft answer goes through the deterministic Claim Verifier
    final_answer, verified, unmatched = verify_claims(draft_answer, tool_outputs)
    
    return AgentChatResponse(
        answer=final_answer,
        verified_claims=verified,
        unmatched_numbers_flagged=unmatched
    )
