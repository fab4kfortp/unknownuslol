"""Fixture-backed stateless implementation of the frozen engine protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from contracts.schemas import LockedPath, Scenario, Transaction

UserData = dict[str, Any]


class MockEngine:
    """Return the Day-One JSON fixtures until the real engine is available."""
    _fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"

    @classmethod
    def _fixture(cls, name: str) -> dict[str, Any]:
        with (cls._fixtures_dir / name).open(encoding="utf-8") as fixture_file:
            return json.load(fixture_file)

    def ingest(self, rows: list[dict[str, Any]], source: str) -> dict[str, Any]:
        return self._fixture("ingest.bad_rows.json")

    def analyze(self, user_data: UserData) -> dict[str, Any]:
        return self._fixture("analysis.persona_b.json")

    def forecast(self, user_data: UserData, horizon_days: int) -> dict[str, Any]:
        return self._fixture("insufficient_data.json")

    def simulate(self, user_data: UserData, scenario: Scenario) -> dict[str, Any]:
        return self._fixture("simulate.new_emi.json")

    def compare_paths(self, user_data: UserData, scenarios: list[Scenario]) -> dict[str, Any]:
        base = self._fixture("simulate.new_emi.json")
        paths = []
        for index, scenario in enumerate(scenarios[:3]):
            path = base.copy()
            path["shortfall_prob"] = (0.12, 0.18, 0.44)[index]
            path["new_dti"] = (0.29, 0.34, 0.51)[index]
            path["runway_days"] = (96, 74, 32)[index]
            path["buffer"] = (
                {"p10": 8200.0, "p50": 22400.0, "p90": 37400.0},
                base["buffer"],
                {"p10": 1100.0, "p50": 7400.0, "p90": 18200.0},
            )[index]
            path["evidence"] = [f"scenario:{scenario.kind}"]
            paths.append(path)
        return {"results": paths, "recommended_path": scenarios[0].kind if scenarios else ""}

    def shock_capacity(self, user_data: UserData, limit: float = 0.10) -> dict[str, Any]:
        return self._fixture("shock_capacity.json")

    def optimize(self, user_data: UserData, target_risk: float) -> dict[str, Any]:
        drift = self._fixture("drift.lp_1.json")
        return {"recovery": drift["recovery"], "tag": "recommended", "evidence": ["lock:lp_1"]}

    def evaluate_lock(self, user_data: UserData, locked_path: LockedPath) -> dict[str, Any]:
        return self._fixture("drift.lp_1.json")

    def refresh(self, user_data: UserData, new_txn: Transaction, locks: list[LockedPath]) -> dict[str, Any]:
        return {
            "transaction": new_txn.model_dump(mode="json"),
            "analysis": self._fixture("analysis.persona_b.json"),
            "drift_results": [self._fixture("drift.lp_1.json")] if locks else [],
            "recommendation": "Protect the locked path by applying the recommended recovery option.",
        }
