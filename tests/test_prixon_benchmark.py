import asyncio
from collections import deque

from prixon.benchmark import benchmark_runtime, summarize_benchmark_rows
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

def test_runtime_benchmark_uses_preview_only_and_captures_local_model_usage():
    class FakeOllama:
        model = "local-test-model"
        base_url = "http://127.0.0.1:11434"
        call_count = 0
        metrics_history = deque(maxlen=10)

    class ForbiddenExecutor:
        def execute_action(self, *args, **kwargs):
            raise AssertionError("Preview benchmark must never execute an action.")

        def execute_plan(self, *args, **kwargs):
            raise AssertionError("Preview benchmark must never execute a plan.")

    class FakeRuntime:
        def __init__(self):
            self.ollama = FakeOllama()
            self.executor = ForbiddenExecutor()

        async def preview(self, text):
            self.ollama.call_count += 1
            self.ollama.metrics_history.append({
                "call_index": self.ollama.call_count,
                "prompt_eval_count": 11,
                "eval_count": 4,
            })
            return {
                "status": "selected",
                "action": "system.status",
                "reason": "rules_first_registry_match",
            }

    runtime = FakeRuntime()
    report = asyncio.run(benchmark_runtime(runtime, [{
        "text": "show system health",
        "expected_action": "system.status",
        "split": "frozen",
        "case_type": "clean",
    }]))
    assert report["mode"] == "preview_only_no_actions_executed"
    assert report["summary"]["requests"] == 1
    assert report["summary"]["accuracy"] == 1.0
    assert report["summary"]["llm_calls"] == 1
    assert report["summary"]["prompt_tokens"] == 11
    assert report["summary"]["completion_tokens"] == 4
    assert report["by_split"]["frozen"]["requests"] == 1
