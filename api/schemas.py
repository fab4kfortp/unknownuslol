from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import date


# 1. Element Tags and Data States
class ElementTag(str, Enum):
    observed = "observed"
    predicted = "predicted"
    recommended = "recommended"


class DataState(str, Enum):
    ok = "ok"
    insufficient_data = "insufficient_data"
    needs_review = "needs_review"


# 2. Twin Forecast
class DailyForecast(BaseModel):
    date: date
    p10: float
    p50: float
    p90: float


class ForecastMetrics(BaseModel):
    mae: float
    mase: float
    coverage: float
    interval_width: float


class TwinForecastResponse(BaseModel):
    forecasts: List[DailyForecast]
    metrics: ForecastMetrics


# 3. Decision Simulator
class SimulatorPreset(str, Enum):
    do_nothing = "do_nothing"
    cut_spend = "cut_spend"
    refinance = "refinance"
    buy_or_new_emi = "buy_or_new_emi"
    medical_emergency = "medical_emergency"
    income_drop_30 = "income_drop_30"
    job_loss = "job_loss"
    emi_hike_12 = "emi_hike_12"


class SimulatorPriority(str, Enum):
    safest = "safest"
    cheapest = "cheapest"


class SimulatorRequest(BaseModel):
    presets: List[SimulatorPreset] = Field(default_factory=list)
    priority: SimulatorPriority = SimulatorPriority.safest
    # Additional optional context for stress tests/presets
    custom_amount: Optional[float] = None
    custom_months: Optional[int] = None


class BufferQuantiles(BaseModel):
    p10: float
    p50: float
    p90: float


class SimulatorPathOutput(BaseModel):
    preset: SimulatorPreset
    shortfall_prob_90d: float
    buffer: BufferQuantiles
    survival_runway_days: int
    months_of_expenses_buffer: float
    goal_delay_weeks: int
    new_dti: float
    new_borrowing_prob_90d: float
    rollover_warning: bool
    one_line_reason: str


class SimulatorResponse(BaseModel):
    recommended_path: SimulatorPreset
    paths: List[SimulatorPathOutput]


# 4. Minimum-Change Optimizer
class OptimizerConstraints(BaseModel):
    target_shortfall_prob: float = 0.10
    min_p10_buffer_amount: float = 0.0
    max_dti: float = 0.40


class OptimizerRequest(BaseModel):
    target_purchase_amount: float
    target_purchase_months: int
    constraints: OptimizerConstraints = Field(default_factory=OptimizerConstraints)


class OptimizerLevers(BaseModel):
    cut_spend_percentages: Dict[str, float]
    purchase_delay_weeks: int
    extra_monthly_saving: float
    amount_drawn_from_savings: float


class OptimizerResponse(BaseModel):
    plan_found: bool
    levers: Optional[OptimizerLevers] = None
    resulting_shortfall_prob: Optional[float] = None
    lifestyle_disruption_score: Optional[float] = None
    explanation: Optional[str] = None


# 5. Categoriser Review Queue and Agent Chat / Live-Update
class ReviewQueueItem(BaseModel):
    transaction_id: str
    description: str
    amount: float
    date: date
    predicted_category: str
    confidence_score: float
    state: DataState = DataState.needs_review


class ReviewQueueResponse(BaseModel):
    items: List[ReviewQueueItem]


class ReviewCorrectionRequest(BaseModel):
    transaction_id: str
    corrected_category: str


class AgentChatRequest(BaseModel):
    query: str
    context_data: Optional[Dict[str, Any]] = None


class AgentChatResponse(BaseModel):
    answer: str
    verified_claims: bool
    unmatched_numbers_flagged: List[str] = Field(default_factory=list)


class TransactionInput(BaseModel):
    description: str
    amount: float
    date: date
    transaction_type: str  # e.g., 'credit' or 'debit'
    category: Optional[str] = None


class LiveTransactionRequest(BaseModel):
    transaction: TransactionInput
    # Included to recalculate specific simulation presets upon live-update
    active_presets: Optional[List[SimulatorPreset]] = None


class LiveTransactionResponse(BaseModel):
    transaction_id: str
    categorised_as: str
    confidence: float
    state: DataState
    # Return updated twin and simulator numbers to immediately refresh the UI
    updated_twin: Optional[TwinForecastResponse] = None
    updated_simulation: Optional[SimulatorResponse] = None
