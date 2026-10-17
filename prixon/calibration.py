from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prixon.confidence import (
    DEFAULT_WEIGHTS,
    RISK_THRESHOLDS,
    DecisionSignals,
    fit_logistic_weights,
    fit_risk_thresholds,
    fuse_confidence,
)
from prixon.store import AgentStore


def build_calibration_proposal(
    reviewed_rows: list[dict[str, Any]],
    *,
    current_weights: dict[str, float] | None = None,
    max_wrong_execution_rate: float = 0.02,
) -> dict[str, Any]:
    """Fit a review-only policy proposal; never activates policy by itself."""
    if not 0.0 <= max_wrong_execution_rate < 1.0:
        raise ValueError("max_wrong_execution_rate must be in [0, 1).")
    usable: list[tuple[DecisionSignals, int, str, float]] = []
    for row in reviewed_rows:
        decision = row.get("decision") or {}
        outcome = row.get("outcome") or {}
        if decision.get("status") != "selected":
            continue
        signals = decision.get("confidence_signals")
        risk = str(decision.get("risk") or "")
        if not isinstance(signals, dict) or risk not in RISK_THRESHOLDS:
            continue
        try:
            signal_object = DecisionSignals(**{
                key: float(signals[key]) for key in DEFAULT_WEIGHTS
            })
        except (KeyError, TypeError, ValueError):
            continue
        usable.append((
            signal_object,
            int(bool(row.get("correct"))),
            risk,
            float(decision.get("confidence") or 0.0),
        ))

    if len(usable) < 20:
        raise ValueError(
            f"At least 20 owner-reviewed selected decisions are required; found {len(usable)}."
        )

    weight_rows = [(signals, label) for signals, label, _, _ in usable]
    proposed_weights = fit_logistic_weights(weight_rows)
    baseline_weights = {
        key: float((current_weights or DEFAULT_WEIGHTS).get(key, DEFAULT_WEIGHTS[key]))
        for key in DEFAULT_WEIGHTS
    }

    def evaluate_weights(weights: dict[str, float]) -> list[tuple[float, bool, str]]:
        return [
            (fuse_confidence(signals, weights), bool(label), risk)
            for signals, label, risk, _ in usable
        ]

    baseline_predictions = evaluate_weights(baseline_weights)
    proposed_predictions = evaluate_weights(proposed_weights)
    threshold_proposal = fit_risk_thresholds(
        proposed_predictions,
        max_wrong_execution_rate=max_wrong_execution_rate,
    )

    def gate_report(
        predictions: list[tuple[float, bool, str]],
        thresholds: dict[str, Any],
    ) -> dict[str, Any]:
        selected = [
            (score, correct) for score, correct, risk in predictions
            if score >= float(thresholds.get(risk, RISK_THRESHOLDS.get(risk, 1.01)))
            and risk != "always_confirm"
        ]
        wrong = sum(not correct for _, correct in selected)
        return {
            "owner_reviewed_selected": len(predictions),
            "autonomous_selected": len(selected),
            "owner_marked_wrong": wrong,
            "wrong_execution_rate": round(wrong / len(selected), 4) if selected else 0.0,
        }

    proposed_threshold_values = {
        tier: float(item["threshold"])
        for tier, item in threshold_proposal.items()
    }
    baseline_report = gate_report(baseline_predictions, RISK_THRESHOLDS)
    proposed_report = gate_report(proposed_predictions, proposed_threshold_values)
    return {
        "status": "ready_for_owner_review",
        "proposal_id": uuid.uuid4().hex,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "explicit_owner_reviewed_decisions_only",
        "owner_reviewed_samples": len(usable),
        "samples_by_risk": {
            tier: sum(1 for _, _, risk, _ in usable if risk == tier)
            for tier in RISK_THRESHOLDS
        },
        "max_wrong_execution_rate": max_wrong_execution_rate,
        "baseline_weights": baseline_weights,
        "weights": proposed_weights,
        "risk_thresholds": threshold_proposal,
        "baseline_labeled_subset": baseline_report,
        "proposed_labeled_subset": proposed_report,
        "deployment_gate": {
            "active": False,
            "requires_owner_confirmation": True,
            "requires_frozen_regression_pass": True,
            "requires_external_frozen_accuracy_before_after": True,
            "requires_wrong_execution_rate_at_or_below_target": True,
            "l4_always_confirms": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create an inactive confidence calibration proposal from owner-reviewed decisions.",
    )
    parser.add_argument("--max-wrong-execution-rate", type=float, default=0.02)
    parser.add_argument("--output", default="artifacts/prixon-calibration-proposal.json")
    args = parser.parse_args()

    store = AgentStore()
    proposal = build_calibration_proposal(
        store.owner_labeled_decisions(limit=20000),
        current_weights=store.get_setting("confidence.active_weights", DEFAULT_WEIGHTS),
        max_wrong_execution_rate=args.max_wrong_execution_rate,
    )
    store.set_setting("confidence.calibration.latest", proposal)
    store.audit("confidence_calibration_proposed", {
        "proposal_id": proposal["proposal_id"],
        "owner_reviewed_samples": proposal["owner_reviewed_samples"],
        "max_wrong_execution_rate": args.max_wrong_execution_rate,
    })
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": proposal["status"],
        "proposal_id": proposal["proposal_id"],
        "owner_reviewed_samples": proposal["owner_reviewed_samples"],
        "weights": proposal["weights"],
        "risk_thresholds": proposal["risk_thresholds"],
        "output": str(output),
    }, indent=2))


if __name__ == "__main__":
    main()
