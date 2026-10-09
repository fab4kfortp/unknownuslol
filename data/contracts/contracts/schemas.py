"""Pydantic v2 contracts for the stateless SpendShield engine."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Tag = Literal["observed", "predicted", "recommended"]


class Transaction(BaseModel):
    id: str
    date: date
    narration: str
    amount: float = Field(gt=0)
    type: Literal["debit", "credit"]
    category: str = "uncategorised"
    category_confidence: float = Field(default=0.0, ge=0, le=1)
    priority: Literal["Critical", "High", "Medium", "Low"] = "Low"
    balance: float | None = None
    is_duplicate: bool = False

    @field_validator("narration")
    @classmethod
    def narration_is_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("narration must not be blank")
        return value


class Scenario(BaseModel):
    kind: Literal[
        "do_nothing",
        "cut_spend",
        "refinance",
        "new_emi",
        "purchase",
        "medical",
        "income_drop_30",
        "job_loss",
        "emi_hike_12",
    ] = "do_nothing"
    params: dict[str, Any] = Field(default_factory=dict)
    horizon_days: int = Field(default=90, ge=14, le=365)
    seed: int = 42


class BufferQuantiles(BaseModel):
    p10: float
    p50: float
    p90: float


class SimulationResult(BaseModel):
    status: Literal["ok", "insufficient_data"]
    shortfall_prob: float = Field(ge=0, le=1)
    buffer: BufferQuantiles
    runway_days: int = Field(ge=0)
    new_dti: float | None = Field(default=None, ge=0)
    tag: Tag = "predicted"
    evidence: list[str] = Field(default_factory=list)
    kind: str = "do_nothing"


class Alert(BaseModel):
    id: str
    mode: Literal["silent_creep", "rollover", "plan_drift"]
    title: str
    extra_per_month: float = Field(default=0, ge=0)
    extra_per_year: float = Field(default=0, ge=0)
    severity: Literal["low", "medium", "high", "critical"]
    evidence: list[str] = Field(default_factory=list)
    tag: Tag = "observed"


class RecurringPayment(BaseModel):
    """Normalised output of the recurring-payment detector."""

    merchant: str
    recurring_type: str
    occurrences: int = Field(ge=3)
    avg_amount: float = Field(ge=0)
    amount_std: float = Field(ge=0)
    avg_interval_days: float = Field(ge=0)
    first_seen: date
    last_seen: date
    first_amount: float = Field(ge=0)
    last_amount: float = Field(ge=0)
    total_drift_pct: float
    evidence: list[str] = Field(default_factory=list)
    tag: Tag = "observed"


class LockedPath(BaseModel):
    id: str
    goal: str
    deadline: date
    required_balance: float = Field(ge=0)
    band: BufferQuantiles
    category_ceilings: dict[str, float] = Field(default_factory=dict)
    max_risk: float = Field(default=0.15, ge=0, le=1)
    priority: Literal["Critical", "High", "Medium", "Low"] = "High"


class RecoveryOption(BaseModel):
    action: Literal["cut", "delay", "reduce_budget"]
    target: str | None = None
    amount: float | None = Field(default=None, ge=0)
    days: int | None = Field(default=None, ge=0)


class DriftResult(BaseModel):
    lock_id: str
    success_prob_before: float = Field(ge=0, le=1)
    success_prob_now: float = Field(ge=0, le=1)
    reason: str
    delay_days: int = Field(ge=0)
    recovery: list[RecoveryOption] = Field(default_factory=list)
    tag: Tag = "recommended"
  
