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
            if not isinstance(row.get("text"), str) or not isinstance(row.get("expected_action"), str):
                raise ValueError(f"Missing text/expected_action at line {line_number}")
            rows.append(row)
    return rows


def evaluate_rows(
    rows: list[dict[str, Any]], router: IntentRouter | None = None,
) -> dict[str, Any]:
    router = router or IntentRouter(ActionRegistry())
    total, correct = 0, 0
    unresolved, clarified = 0, 0
    per_action: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "correct": 0})
    confusions: dict[str, int] = defaultdict(int)
    frozen_total, frozen_correct = 0, 0
    for row in rows:
        expected = row["expected_action"]
        result = router.route(row["text"])
        predicted = result.selected_action
        total += 1
        per_action[expected]["total"] += 1
        if result.status == "unresolved":
            unresolved += 1
        elif result.status == "clarify":
            clarified += 1
        if predicted == expected:
            correct += 1
            per_action[expected]["correct"] += 1
        else:
            confusions[f"{expected} -> {predicted or result.status}"] += 1
        if row.get("split") == "frozen":
            frozen_total += 1
            frozen_correct += int(predicted == expected)
    return {
        "total": total,
        "correct": correct,
        "action_accuracy": round(correct / total, 4) if total else 0.0,
        "unresolved": unresolved,
        "clarified": clarified,
        "frozen_total": frozen_total,
        "frozen_accuracy": round(frozen_correct / frozen_total, 4) if frozen_total else None,
        "per_action": {
            action: {
                **counts,
                "accuracy": round(counts["correct"] / counts["total"], 4) if counts["total"] else 0,
            }
            for action, counts in per_action.items()
        },
        "top_confusions": sorted(confusions.items(), key=lambda item: item[1], reverse=True)[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Prixon intent routing on the frozen JSONL dataset.")
    parser.add_argument(
        "--dataset", default="tests/data/prixon_eval.jsonl",
        help="Path to the frozen JSONL evaluation set.",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_rows(load_dataset(args.dataset)), indent=2))


if __name__ == "__main__":
    main()
