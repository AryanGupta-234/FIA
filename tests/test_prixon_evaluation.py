from pathlib import Path

from prixon.evaluation import evaluate_rows, load_dataset
from prixon.registry import ActionRegistry
from prixon.router import IntentRouter


def test_frozen_dataset_has_several_hundred_examples():
    rows = load_dataset(Path(__file__).parent / "data" / "prixon_eval.jsonl")
    assert len(rows) >= 200
    report = evaluate_rows(rows, IntentRouter(ActionRegistry()))
    assert report["action_accuracy"] >= 0.80
    assert report["frozen_total"] > 0


def test_evaluation_reports_class_confusions():
    rows = [
        {"text": "show system health", "expected_action": "system.status"},
        {"text": "list running processes", "expected_action": "process.list"},
    ]
    report = evaluate_rows(rows)
    assert report["total"] == 2
    assert report["correct"] == 2
