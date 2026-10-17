from pathlib import Path

from prixon.evaluation import evaluate_rows, load_dataset
from prixon.registry import ActionRegistry
from prixon.router import IntentRouter


def test_frozen_dataset_has_several_hundred_diverse_examples():
    rows = load_dataset(Path(__file__).parent / "data" / "prixon_eval.jsonl")
    assert len(rows) >= 300
    assert {row.get("case_type") for row in rows} >= {
        "clean", "noisy", "pronoun", "compound", "ambiguous", "adversarial", "lookalike",
    }
    report = evaluate_rows(rows, IntentRouter(ActionRegistry()))
    assert report["action_and_status_accuracy"] >= 0.80
    assert report["frozen_total"] > 0
    assert report["per_case_type"]["ambiguous"]["accuracy"] >= 0.80


def test_evaluation_reports_wrong_selection_separately_from_abstention():
    rows = [
        {"text": "show system health", "expected_action": "system.status"},
        {"text": "open", "expected_status": "clarify"},
    ]
    report = evaluate_rows(rows)
    assert report["selected_action_count"] == 1
    assert report["wrong_selected_action_count"] == 0
    assert report["wrong_selection_rate_when_selected"] == 0.0


def test_evaluation_reports_routing_class_and_clarification_metrics():
    rows = [
        {"text": "show system health", "expected_action": "system.status", "case_type": "clean"},
        {"text": "open", "expected_status": "clarify", "case_type": "ambiguous"},
    ]
    report = evaluate_rows(rows)
    assert report["total"] == 2
    assert report["correct"] == 2
    assert "query" in report["per_intent_class"]
    assert report["clarification_rate"] == 0.5
