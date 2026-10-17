from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionSignals:
    retrieval_margin: float
    slot_grounding: float
    llm_confidence: float = 0.0
    context_prior: float = 0.0
    user_lexicon_hit: float = 0.0


DEFAULT_WEIGHTS = {
    "retrieval_margin": 0.30,
    "slot_grounding": 0.25,
    "llm_confidence": 0.10,
    "context_prior": 0.10,
    "user_lexicon_hit": 0.25,
}
RISK_THRESHOLDS = {
    "read_only": 0.55,
    "reversible": 0.72,
    "allowlisted_routine": 0.84,
    "always_confirm": 1.01,
}


def fuse_confidence(
    signals: DecisionSignals, weights: dict[str, float] | None = None,
) -> float:
    selected = weights or DEFAULT_WEIGHTS
    total = sum(max(0.0, selected.get(name, 0.0)) for name in DEFAULT_WEIGHTS)
    if total <= 0:
        raise ValueError("At least one non-negative confidence weight is required")
    score = sum(
        max(0.0, min(1.0, getattr(signals, name))) * max(0.0, selected.get(name, 0.0))
        for name in DEFAULT_WEIGHTS
    ) / total
    return round(max(0.0, min(1.0, score)), 4)


def meets_risk_threshold(score: float, risk_tier: str) -> bool:
    if risk_tier == "always_confirm":
        return False
    return score >= RISK_THRESHOLDS.get(risk_tier, 1.01)


def fit_logistic_weights(
    rows: list[tuple[DecisionSignals, int]], epochs: int = 400, learning_rate: float = 0.08,
) -> dict[str, float]:
    """Fit non-negative logistic coefficients from owner-reviewed decision outcomes."""
    if len(rows) < 20:
        raise ValueError("At least 20 labeled outcomes are required for weight fitting")
    names = list(DEFAULT_WEIGHTS)
    values = [[getattr(signals, name) for name in names] for signals, _ in rows]
    labels = [label for _, label in rows]
    if any(label not in (0, 1) for label in labels):
        raise ValueError("Outcome labels must be binary")
    weights = [DEFAULT_WEIGHTS[name] for name in names]
    bias = 0.0
    for _ in range(epochs):
        grad = [0.0] * len(names)
        grad_bias = 0.0
        for vector, label in zip(values, labels, strict=True):
            logit = max(-30.0, min(30.0, bias + sum(w * x for w, x in zip(weights, vector, strict=True))))
            probability = 1.0 / (1.0 + math.exp(-logit))
            error = probability - label
            grad_bias += error
            for index, value in enumerate(vector):
                grad[index] += error * value
        scale = 1.0 / len(rows)
        bias -= learning_rate * grad_bias * scale
        weights = [
            max(0.0, weight - learning_rate * gradient * scale)
            for weight, gradient in zip(weights, grad, strict=True)
        ]
    total = sum(weights)
    if total <= 0:
        return DEFAULT_WEIGHTS.copy()
    return {name: round(weight / total, 4) for name, weight in zip(names, weights, strict=True)}
