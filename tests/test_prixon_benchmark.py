from prixon.benchmark import summarize_benchmark_rows
from prixon.ollama import OllamaClient


def test_ollama_metrics_summary_reports_success_and_failed_attempts():
    client = OllamaClient()
    client.call_count = 3
    client.metrics_history.extend([
        {"call_index": 1, "success": True, "latency_ms": 10.0,
         "prompt_eval_count": 5, "eval_count": 2},
        {"call_index": 2, "success": False, "latency_ms": 30.0,
         "error": "ReadTimeout"},
        {"call_index": 3, "success": True, "latency_ms": 20.0,
         "prompt_eval_count": 7, "eval_count": 4},
    ])
    summary = client.metrics_summary()
    assert summary["total_calls"] == 3
    assert summary["failed_calls"] == 1
    assert summary["success_rate"] == 0.6667
    assert summary["latency_p50_ms"] == 20.0
    assert summary["latency_p95_ms"] == 30.0
    assert summary["prompt_tokens_total"] == 12
    assert summary["completion_tokens_total"] == 6


def test_benchmark_summary_calculates_latency_and_local_model_share():
    rows = [
        {"latency_ms": 10.0, "status": "selected", "action": "a", "correct": True, "llm_calls": 1,
         "prompt_tokens": 5, "completion_tokens": 3},
        {"latency_ms": 20.0, "status": "clarify", "action": None, "correct": True, "llm_calls": 0},
        {"latency_ms": 30.0, "status": "selected", "action": "b", "correct": False, "wrong_selection": True,
         "llm_calls": 2, "prompt_tokens": 8, "completion_tokens": 4},
        {"latency_ms": 40.0, "status": "unresolved", "action": None, "correct": False, "llm_calls": 0},
    ]
    report = summarize_benchmark_rows(rows)
    assert report["requests"] == 4
    assert report["accuracy"] == 0.5
    assert report["wrong_selection_rate_per_request"] == 0.25
    assert report["wrong_selection_rate_when_selected"] == 0.5
    assert report["llm_request_share"] == 0.5
    assert report["llm_calls"] == 3
    assert report["latency_ms"] == {"p50": 20.0, "p95": 40.0, "mean": 25.0, "max": 40.0}
    assert report["prompt_tokens"] == 13
    assert report["completion_tokens"] == 7
