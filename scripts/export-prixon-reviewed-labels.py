from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from prixon.registry import ActionRegistry
from prixon.store import AgentStore


SENSITIVE_TERMS = (
    "password", "passphrase", "secret", "api key", "access token",
    "credential", "otp", "one time password", "recovery code",
)
URL_OR_PATH = re.compile(r"(?:https?://|(?:[a-zA-Z]:\\\\)|/home/|/users/)", re.IGNORECASE)


def export_reviewed_aliases(database: str | None = None) -> list[dict[str, object]]:
    store = AgentStore(database)
    registry = ActionRegistry()
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for alias in store.aliases():
        if not alias.get("explicit") or alias.get("target_type") != "action":
            continue
        phrase = " ".join(str(alias.get("phrase") or "").split())
        action_name = str(alias.get("target") or "")
        action = registry.get(action_name)
        lowered = phrase.casefold()
        if (
            action is None
            or len(phrase) < 3
            or len(phrase) > 180
            or URL_OR_PATH.search(phrase)
            or any(term in lowered for term in SENSITIVE_TERMS)
        ):
            continue
        key = (action_name, lowered)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "text": phrase,
            "expected_action": action_name,
            "intent_class": action.intent_class.value,
            "risk": action.risk.value,
            "requires_confirmation": action.risk.value == "always_confirm",
            "source": "owner_explicit_or_approved_alias",
            "owner_reviewed": True,
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export only explicitly taught/owner-approved Prixon action labels for optional LoRA research."
    )
    parser.add_argument("--db", help="Optional Prixon SQLite database path.")
    parser.add_argument("--output", default="artifacts/prixon-reviewed-lora.jsonl")
    args = parser.parse_args()
    rows = export_reviewed_aliases(args.db)
    if len(rows) < 5:
        raise SystemExit(
            f"Only {len(rows)} owner-reviewed action aliases are available; teach/approve more before LoRA training."
        )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    print(f"Exported {len(rows)} owner-reviewed action labels to {output}")


if __name__ == "__main__":
    main()
