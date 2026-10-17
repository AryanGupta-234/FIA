from __future__ import annotations

from typing import Any

FAILURE_CAUSES = (
    "wrong_target",
    "app_not_ready",
    "permission",
    "timing",
    "missing_prerequisite",
    "stale_entity",
    "postcondition_mismatch",
    "unknown",
)


def normalize_reflection(raw: dict[str, Any]) -> dict[str, Any]:
    cause = str(raw.get("likely_cause", "unknown")).casefold()
    if cause not in FAILURE_CAUSES:
        cause = "unknown"
    alternative = str(raw.get("alternative_action", "")).strip()
    return {
        "what_failed": str(raw.get("what_failed", ""))[:300],
        "likely_cause": cause,
        "alternative_action": alternative[:100],
        "confidence": max(0.0, min(1.0, float(raw.get("confidence", 0.0) or 0.0))),
    }
