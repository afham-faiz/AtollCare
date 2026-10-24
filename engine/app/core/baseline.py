# F-M2.9 Baseline comparison — sequential phone chain (DEMO ASSUMPTION, baseline.yaml) vs our parallel flow.
from __future__ import annotations

from datetime import datetime

from app.core import refdata
from app.models import BaselineComparison, BaselineStep, RouteOption


def compare(
    route: RouteOption | None, submitted_at: datetime | None, accepted_at: datetime | None
) -> BaselineComparison:
    cfg = refdata.baseline_config()
    route_min = route.total_min if route else 0.0
    steps: list[BaselineStep] = []
    for s in cfg["steps"]:
        minutes = route_min if s["min"] == "route.total_min" else float(s["min"])
        steps.append(BaselineStep(id=s["id"], label=s["label"], min=round(minutes, 1)))
    baseline_total = sum(s.min for s in steps)
    overhead = float(cfg.get("ours_parallel_overhead_min", 10))
    measured = False
    if submitted_at and accepted_at and accepted_at >= submitted_at:
        overhead = round((accepted_at - submitted_at).total_seconds() / 60, 1)
        measured = True
    ours_steps = [
        BaselineStep(
            id="referral_acceptance",
            label="Referral + acceptance in parallel" + (" (measured)" if measured else " (assumed)"),
            min=overhead,
        ),
        BaselineStep(id="transport", label="Transport (recommended route)", min=round(route_min, 1)),
    ]
    ours_total = overhead + route_min
    return BaselineComparison(
        steps=steps,
        baseline_total_min=round(baseline_total, 1),
        ours_steps=ours_steps,
        ours_total_min=round(ours_total, 1),
        saved_vs_baseline_min=round(baseline_total - ours_total, 1),
        coordination_measured=measured,
        assumptions={
            "source": "engine/app/data/baseline.yaml",
            "label": "DEMO ASSUMPTION",
            "steps": {s["id"]: s["min"] for s in cfg["steps"]},
            "ours_parallel_overhead_min": cfg.get("ours_parallel_overhead_min", 10),
        },
    )
