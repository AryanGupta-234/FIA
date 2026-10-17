from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prixon.registry import ActionRegistry


PROMPT_PREFIX = (
    "You are Prixon's local intent label adapter. Select the registered action ID "
    "that best matches the owner request. Return only the action ID. Never create "
    "commands, scripts, tools or permissions.\nOwner request: "
)
PROMPT_SUFFIX = "\nRegistered action ID:"


def load_rows(path: Path, registry: ActionRegistry) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row: dict[str, Any] = json.loads(line)
        action = str(row.get("expected_action") or "")
        phrase = str(row.get("text") or "").strip()
        if (
            row.get("owner_reviewed") is not True
            or row.get("source") != "owner_explicit_or_approved_alias"
            or not phrase
            or registry.get(action) is None
        ):
            raise ValueError(f"Unreviewed or invalid training row at line {line_number}")
        rows.append({"text": phrase, "label": action})
    if len(rows) < 5:
        raise ValueError("At least five owner-reviewed labels are required.")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train a separate PEFT LoRA adapter from owner-reviewed labels only."
    )
    parser.add_argument("--base-model", required=True, help="Local Hugging Face model directory; remote downloads are disabled.")
    parser.add_argument("--dataset", default="artifacts/prixon-reviewed-lora.jsonl")
    parser.add_argument("--output", default="artifacts/prixon-lora-adapter")
    parser.add_argument("--epochs", type=float, default=3.0)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--target-modules", default="q_proj,k_proj,v_proj,o_proj")
    args = parser.parse_args()

    base = Path(args.base_model).expanduser().resolve()
    if not base.is_dir():
        raise SystemExit("The base model must be a local directory; remote model downloads are disabled.")
    rows = load_rows(Path(args.dataset), ActionRegistry())
    if len(rows) < 10:
        raise SystemExit("At least ten reviewed examples are needed to reserve a validation split.")

    try:
        import torch
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        raise SystemExit("Install the optional .[lora] extra before training.") from exc

    tokenizer = AutoTokenizer.from_pretrained(str(base), local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    class ReviewedDataset(torch.utils.data.Dataset):
        def __init__(self, examples):
            self.items = []
            for row in examples:
                prompt = PROMPT_PREFIX + row["text"] + PROMPT_SUFFIX
                prompt_ids = tokenizer(
                    prompt, truncation=True, max_length=args.max_length,
                    add_special_tokens=True,
                )["input_ids"]
                target_ids = tokenizer(
                    " " + row["label"] + tokenizer.eos_token,
                    truncation=True, max_length=40, add_special_tokens=False,
                )["input_ids"]
                ids = prompt_ids + target_ids
                labels = [-100] * len(prompt_ids) + target_ids
                self.items.append((ids, labels))

        def __len__(self):
            return len(self.items)

        def __getitem__(self, index):
            ids, labels = self.items[index]
            return {
                "input_ids": torch.tensor(ids, dtype=torch.long),
                "attention_mask": torch.ones(len(ids), dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long),
            }

    class PadCollator:
        def __call__(self, batch):
            max_len = max(item["input_ids"].shape[0] for item in batch)
            ids, masks, labels = [], [], []
            for item in batch:
                missing = max_len - item["input_ids"].shape[0]
                ids.append(torch.nn.functional.pad(
                    item["input_ids"], (0, missing), value=tokenizer.pad_token_id,
                ))
                masks.append(torch.nn.functional.pad(
                    item["attention_mask"], (0, missing), value=0,
                ))
                labels.append(torch.nn.functional.pad(
                    item["labels"], (0, missing), value=-100,
                ))
            return {
                "input_ids": torch.stack(ids),
                "attention_mask": torch.stack(masks),
                "labels": torch.stack(labels),
            }

    split = max(1, int(len(rows) * 0.1))
    train_rows, eval_rows = rows[:-split], rows[-split:]
    model = AutoModelForCausalLM.from_pretrained(
        str(base), local_files_only=True, torch_dtype="auto",
    )
    model.config.use_cache = False
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=[item.strip() for item in args.target_modules.split(",") if item.strip()],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=args.output,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=5,
        save_strategy="epoch",
        evaluation_strategy="epoch",
        report_to=[],
        remove_unused_columns=False,
        fp16=False,
        bf16=False,
        optim="adamw_torch",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ReviewedDataset(train_rows),
        eval_dataset=ReviewedDataset(eval_rows),
        data_collator=PadCollator(),
    )
    trainer.train()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output)
    tokenizer.save_pretrained(output)
    manifest = {
        "adapter_type": "peft_lora",
        "base_model_local_path": str(base),
        "reviewed_examples": len(rows),
        "train_examples": len(train_rows),
        "validation_examples": len(eval_rows),
        "automatic_runtime_activation": False,
        "promotion_requires_frozen_set_evidence": True,
        "frozen_evaluation_dataset": "tests/data/prixon_eval.jsonl",
        "registered_tools_only": True,
    }
    (output / "prixon_lora_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2))
    print("Adapter saved separately; it has not replaced the production Ollama model.")


if __name__ == "__main__":
    main()
