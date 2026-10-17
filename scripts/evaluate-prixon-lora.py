from __future__ import annotations
import argparse, json, statistics, time
from pathlib import Path
from prixon.registry import ActionRegistry
from prixon.evaluation import load_dataset

def main():
    parser = argparse.ArgumentParser(description="Compare local base model and local LoRA adapter on Prixon's frozen benchmark.")
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--dataset", default="tests/data/prixon_eval.jsonl")
    parser.add_argument("--output", default="artifacts/prixon-lora-frozen-comparison.json")
    args = parser.parse_args()
    base = Path(args.base_model).expanduser().resolve()
    adapter = Path(args.adapter).expanduser().resolve()
    if not base.is_dir() or not adapter.is_dir():
        raise SystemExit("Model and adapter must be local directories; network downloads are disabled.")
    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise SystemExit("Install the optional .[lora] extra first.") from exc
    rows = [row for row in load_dataset(args.dataset) if row.get("split") == "frozen"]
    if not rows:
        raise SystemExit("No frozen evaluation examples were found.")
    actions = [item.name for item in ActionRegistry().all()]
    tokenizer = AutoTokenizer.from_pretrained(str(base), local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(str(base), local_files_only=True)
    model = PeftModel.from_pretrained(model, str(adapter), local_files_only=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()
    results = []
    for row in rows:
        prompt = (
            "Classify this Windows request. Output one registered action ID, CLARIFY, or UNRESOLVED. "
            "Do not invent actions.\nRequest: " + row["text"] + "\nAction:"
        )
        inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        started = time.perf_counter()
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=24, do_sample=False, pad_token_id=tokenizer.pad_token_id)
        latency = (time.perf_counter() - started) * 1000
        decoded = tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip().casefold()
        prediction = "UNRESOLVED"
        if decoded.startswith("clarify"):
            prediction = "CLARIFY"
        elif decoded.startswith("unresolved"):
            prediction = "UNRESOLVED"
        else:
            for action in sorted(actions, key=len, reverse=True):
                if decoded.startswith(action.casefold()):
                    prediction = action
                    break
        expected = row.get("expected_action")
        expected_status = row.get("expected_status")
        correct = prediction == expected_status.upper() if expected_status else prediction == expected
        results.append({"text": row["text"], "expected_action": expected, "expected_status": expected_status,
                        "prediction": prediction, "correct": correct, "latency_ms": round(latency, 2)})
    total = len(results)
    selected = [item for item in results if item["prediction"] not in {"CLARIFY", "UNRESOLVED"}]
    wrong = [item for item in selected if (item["expected_action"] and item["prediction"] != item["expected_action"]) or item["expected_status"]]
    latencies = sorted(item["latency_ms"] for item in results)
    report = {
        "evaluation_mode": "frozen_set_only_no_windows_actions",
        "base_model": str(base), "adapter": str(adapter), "frozen_examples": total,
        "accuracy": round(sum(item["correct"] for item in results) / total, 4),
        "wrong_selected_actions": len(wrong),
        "wrong_selection_rate_when_selected": round(len(wrong) / len(selected), 4) if selected else 0.0,
        "clarification_rate": round(sum(item["prediction"] == "CLARIFY" for item in results) / total, 4),
        "latency_p50_ms": latencies[(len(latencies)-1)//2],
        "latency_p95_ms": latencies[min(len(latencies)-1, int(.95*len(latencies)))],
        "cases": results,
        "automatic_promotion": False,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "cases"}, indent=2))
    print("Adapter remains experimental; do not enable unless frozen-set evidence improves safely.")

if __name__ == "__main__":
    main()
