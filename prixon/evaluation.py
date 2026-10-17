from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from prixon.registry import ActionRegistry
from prixon.router import IntentRouter


def load_dataset(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    with Path(path).open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}") from exc
            if not isinstance(row.get("text"), str):
                raise ValueError(f"Missing text at line {line_number}")
            if not isinstance(row.get("expected_action"), str) and not isinstance(row.get("expected_status"), str):
                raise ValueError(f"Missing expected_action/expected_status at line {line_number}")
            rows.append(row)
    return rows


def evaluate_rows(
    rows: list[dict[str, Any]], router: IntentRouter | None = None,
) -> dict[str, Any]:
    router = router or IntentRouter(ActionRegistry())
    total = correct = unresolved = clarified = frozen_total = frozen_correct = 0
    rule_selected = selected_count = wrong_selected_count = safe_abstentions = 0
    per_action: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    per_case: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    per_class: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    confusions: dict[str, int] = defaultdict(int)

    for row in rows:
        route_text = row.get("route_text", row["text"])
        result = router.route(route_text)
        expected_action = row.get("expected_action")
        expected_status = row.get("expected_status")
        if expected_status:
            outcome_correct = result.status == expected_status
            label = f"status:{expected_status}"
        else:
            outcome_correct = result.selected_action == expected_action
            label = str(expected_action)
        total += 1
        per_case[row.get("case_type", "unspecified")]["total"] += 1
        per_case[row.get("case_type", "unspecified")]["correct"] += int(outcome_correct)
        per_class[(result.intent_class.value if result.intent_class else "none")]["total"] += 1
        per_class[(result.intent_class.value if result.intent_class else "none")]["correct"] += int(outcome_correct)
        if expected_action:
            per_action[expected_action]["total"] += 1
            per_action[expected_action]["correct"] += int(outcome_correct)
        if result.status == "unresolved":
            unresolved += 1
        elif result.status == "clarify":
            clarified += 1
        if result.selected_action:
            selected_count += 1
            expected_selection = (
                result.selected_action == expected_action
                if expected_action else expected_status == "selected"
            )
            wrong_selected_count += int(not expected_selection)
        elif expected_action and result.status in {"clarify", "unresolved"}:
            safe_abstentions += 1
        if result.reason == "rules_first_registry_match":
            rule_selected += 1
        if outcome_correct:
            correct += 1
        else:
            confusions[f"{label} -> {result.selected_action or result.status}"] += 1
        if row.get("split") == "frozen":
            frozen_total += 1
            frozen_correct += int(outcome_correct)

    def rates(rows_by_key: dict[str, dict[str, int]]) -> dict[str, dict[str, int | float]]:
        return {
            key: {
                **counts,
                "accuracy": round(counts["correct"] / counts["total"], 4) if counts["total"] else 0.0,
            }
            for key, counts in rows_by_key.items()
        }

    return {
        "total": total,
        "correct": correct,
        "action_and_status_accuracy": round(correct / total, 4) if total else 0.0,
        "clarification_rate": round(clarified / total, 4) if total else 0.0,
        "unresolved_rate": round(unresolved / total, 4) if total else 0.0,
        "l1_rules_selected_share": round(rule_selected / total, 4) if total else 0.0,
        "selected_action_count": selected_count,
        "wrong_selected_action_count": wrong_selected_count,
        "wrong_selection_rate_per_request": round(wrong_selected_count / total, 4) if total else 0.0,
        "wrong_selection_rate_when_selected": (
            round(wrong_selected_count / selected_count, 4) if selected_count else 0.0
        ),
        "safe_abstention_count": safe_abstentions,
        "frozen_total": frozen_total,
        "frozen_accuracy": round(frozen_correct / frozen_total, 4) if frozen_total else None,
        "per_action": rates(per_action),
        "per_case_type": rates(per_case),
        "per_intent_class": rates(per_class),
        "top_confusions": sorted(confusions.items(), key=lambda item: item[1], reverse=True)[:25],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Prixon intent routing on the frozen/growing JSONL set.")
    parser.add_argument("--dataset", default="tests/data/prixon_eval.jsonl")
    args = parser.parse_args()
    report = evaluate_rows(load_dataset(args.dataset))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
