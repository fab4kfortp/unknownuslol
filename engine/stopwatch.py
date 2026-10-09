"""Repeatable engine speed harness.

Run with:
    python -m engine.stopwatch
"""

from __future__ import annotations

from pathlib import Path
from time import perf_counter

import pandas as pd

from .real_engine import RealEngine


def run(path: str | Path | None = None) -> dict[str, float]:
    path = Path(
        path
        or Path(__file__).parents[1]
        / "data"
        / "persona_b_transactions.csv"
    )

    rows = pd.read_csv(path).to_dict(orient="records")
    engine = RealEngine()
    data = engine.ingest(rows)["accepted"]

    started = perf_counter()
    engine.analyze(data)
    analyze_seconds = perf_counter() - started

    started = perf_counter()
    engine.simulate(
        data,
        {"kind": "medical", "params": {"amount": 25_000}},
    )
    simulate_seconds = perf_counter() - started

    return {
        "analyze_seconds": round(analyze_seconds, 4),
        "simulate_seconds": round(simulate_seconds, 4),
    }


if __name__ == "__main__":
    print(run())
