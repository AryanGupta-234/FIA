from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prixon.evaluation import load_dataset
from prixon.runtime import AgentRuntime


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(quantile * len(ordered) + 0.999999) - 1))
    return round(ordered[index], 2)


def summarize_benchmark_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    selected = sum(bool(row.get("action")) for row in rows)
    wrong_selected = sum(bool(row.get("wrong_selection")) for row in rows)
    llm_requests = sum(int(row.get("llm_calls", 0)) > 0 for row in rows)
    latencies = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
    correct = sum(bool(row.get("correct")) for row in rows)
    return {
        "requests": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "selected_actions": selected,
        "wrong_selected_actions": wrong_selected,
        "wrong_selection_rate_per_request": round(wrong_selected / total, 4) if total else 0.0,
        "wrong_selection_rate_when_selected": round(wrong_selected / selected, 4) if selected else 0.0,
        "clarification_rate": (
            round(sum(row.get("status") == "clarify" for row in rows) / total, 4)
            if total else 0.0
        ),
        "unresolved_rate": (
            round(sum(row.get("status") == "unresolved" for row in rows) / total, 4)
            if total else 0.0
        ),
        "llm_requests": llm_requests,
        "llm_request_share": round(llm_requests / total, 4) if total else 0.0,
        "llm_calls": sum(int(row.get("llm_calls", 0)) for row in rows),
        "mean_llm_calls_per_request": (
            round(sum(int(row.get("llm_calls", 0)) for row in rows) / total, 4)
            if total else 0.0
        ),
        "prompt_tokens": sum(int(row.get("prompt_tokens", 0)) for row in rows),
        "completion_tokens": sum(int(row.get("completion_tokens", 0)) for row in rows),
        "json_valid_responses": sum(int(row.get("json_valid_calls", 0)) for row in rows),
        "json_invalid_responses": sum(int(row.get("json_invalid_calls", 0)) for row in rows),
        "json_validity_samples": sum(
            int(row.get("json_valid_calls", 0)) + int(row.get("json_invalid_calls", 0))
            for row in rows
        ),
        "json_validity_rate": (
            round(
                sum(int(row.get("json_valid_calls", 0)) for row in rows)
                / sum(
                    int(row.get("json_valid_calls", 0)) + int(row.get("json_invalid_calls", 0))
                    for row in rows
                ),
                4,
            )
            if sum(
                int(row.get("json_valid_calls", 0)) + int(row.get("json_invalid_calls", 0))
                for row in rows
            ) else None
        ),
        "latency_ms": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "mean": round(statistics.mean(latencies), 2) if latencies else None,
            "max": round(max(latencies), 2) if latencies else None,
        },
        "errors": sum(bool(row.get("error")) for row in rows),
    }


async def benchmark_runtime(
    runtime: AgentRuntime,
    dataset: list[dict[str, Any]],
) -> dict[str, Any]:
    """Benchmark intent preview only; this function never calls the executor."""
    records: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()

    for row in dataset:
        before_calls = int(getattr(runtime.ollama, "call_count", 0))
        started = time.perf_counter()
        try:
            result = await runtime.preview(str(row["text"]))
            error = None
        except Exception as exc:
            result = {"status": "error", "action": None, "reason": "preview_error"}
            error = type(exc).__name__
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        after_calls = int(getattr(runtime.ollama, "call_count", before_calls))
        new_calls = max(0, after_calls - before_calls)
        history = list(getattr(runtime.ollama, "metrics_history", []))
        new_metrics = [
            item for item in history
            if int(item.get("call_index", 0)) > before_calls
        ]
        expected_action = row.get("expected_action")
        expected_status = row.get("expected_status")
        action = result.get("action")
        correct = (
            result.get("status") == expected_status
            if expected_status else result.get("status") == "selected" and action == expected_action
        )
        wrong_selection = bool(action) and (
            action != expected_action if expected_action else expected_status != "selected"
        )
        prompt_tokens = sum(int(item.get("prompt_eval_count") or 0) for item in new_metrics)
        completion_tokens = sum(int(item.get("eval_count") or 0) for item in new_metrics)
        json_valid_calls = sum(item.get("json_valid") is True for item in new_metrics)
        json_invalid_calls = sum(item.get("json_valid") is False for item in new_metrics)
        reason = str(result.get("reason") or result.get("status") or "unknown")
        reasons[reason] += 1
        records.append({
            "split": str(row.get("split", "unspecified")),
            "case_type": str(row.get("case_type", "unspecified")),
            "status": str(result.get("status", "error")),
            "action": action,
            "correct": bool(correct),
            "wrong_selection": wrong_selection,
            "llm_calls": new_calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "json_valid_calls": json_valid_calls,
            "json_invalid_calls": json_invalid_calls,
            "latency_ms": latency_ms,
            "reason": reason,
            "error": error,
        })

    by_split: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_split[record["split"]].append(record)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "preview_only_no_actions_executed",
        "model": getattr(runtime.ollama, "model", "unknown"),
        "endpoint": getattr(runtime.ollama, "base_url", "unknown"),
        "summary": summarize_benchmark_rows(records),
        "by_split": {
            key: summarize_benchmark_rows(items)
            for key, items in sorted(by_split.items())
        },
        "route_reasons": dict(reasons),
    }


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    dataset = load_dataset(args.dataset)
    if args.split != "all":
        dataset = [row for row in dataset if row.get("split") == args.split]
    if args.limit is not None:
        dataset = dataset[:args.limit]
    if not dataset:
        raise ValueError("The selected benchmark split contains no cases.")

    runtime = AgentRuntime()
    try:
        return await benchmark_runtime(runtime, dataset)
    finally:
        runtime.executor.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a preview-only Prixon benchmark using the local Windows runtime.",
    )
    parser.add_argument("--dataset", default="tests/data/prixon_eval.jsonl")
    parser.add_argument("--split", choices=("all", "frozen", "growing"), default="all")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--output", default="artifacts/prixon-benchmark-latest.json")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be greater than zero")

    report = asyncio.run(_run_cli(args))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Full report saved to: {output}")


if __name__ == "__main__":
    main()
