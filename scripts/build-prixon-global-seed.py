from __future__ import annotations

import json
from pathlib import Path

from prixon.registry import ActionRegistry


PREFIXES = (
    "",
    "Hey Prixon, ",
    "Prixon, ",
    "Quick request: ",
    "Please, ",
    "When you have a moment, ",
)
SUFFIXES = (
    "",
    " please",
    " for me",
    " now",
    " when you can",
    " if possible",
    ", thanks",
    ", please",
    " as soon as possible",
    ", thank you",
)


def build_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for action in ActionRegistry().all():
        for source_phrase in action.examples:
            for prefix in PREFIXES:
                for suffix in SUFFIXES:
                    phrase = " ".join(f"{prefix}{source_phrase}{suffix}".split())
                    key = (action.name, phrase.casefold())
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append({
                        "seed_version": "global_seed_v1",
                        "text": phrase,
                        "action_name": action.name,
                        "intent_class": action.intent_class.value,
                        "source_phrase": source_phrase,
                        "variant_style": (
                            "canonical" if not prefix and not suffix
                            else "addressed_and_styled" if prefix and suffix
                            else "addressed" if prefix else "styled"
                        ),
                    })
    return rows


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "prixon" / "data" / "global_seed_v1.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = build_rows()
    output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} global seed examples to {output}")


if __name__ == "__main__":
    main()
