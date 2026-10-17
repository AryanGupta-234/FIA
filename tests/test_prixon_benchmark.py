from prixon.benchmark import summarize_benchmark_rows


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
