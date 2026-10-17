from __future__ import annotations

import time
from difflib import SequenceMatcher
from typing import Any

from prixon.store import AgentStore


class EntityIndex:
    """Incremental index of grounded apps, processes, windows, files and settings."""

    def __init__(self, store: AgentStore) -> None:
        self.store = store

    def refresh(self, kind: str, entities: list[dict[str, Any]], source: str = "perception") -> int:
        count = 0
        for entity in entities:
            name, target = str(entity.get("name", "")).strip(), entity.get("target")
            if not name or not target:
                continue
            self.store.add_entity(kind, name, str(target), source, entity)
            count += 1
        return count

    def resolve(
        self, mention: str, kind: str | None = None, threshold: float = 0.78,
        context_target: str | None = None,
    ) -> dict[str, Any] | None:
        query = " ".join(mention.casefold().split())
        if not query:
            return None
        alias = self.store.alias(query)
        if alias and (kind is None or alias["target_type"] == kind):
            return {
                "kind": alias["target_type"], "name": mention, "target": alias["target"],
                "score": alias["confidence"], "matched_by": "owner_alias",
            }
        best: dict[str, Any] | None = None
        best_score = 0.0
        runner_up = 0.0
        for entity in self.store.entity_rows(kind):
            name = entity["normalized"]
            score = 1.0 if query == name else SequenceMatcher(None, query, name).ratio()
            if context_target and entity["target"] == context_target:
                score = min(1.0, score + 0.04)
            if score > best_score:
                runner_up, best_score, best = best_score, score, entity
            elif score > runner_up:
                runner_up = score
        if best is None or best_score < threshold or best_score - runner_up < 0.06:
            return None
        return {
            "kind": best["kind"], "name": best["name"], "target": best["target"],
            "score": best_score, "matched_by": "exact" if best_score == 1 else "fuzzy",
        }


class ReferenceResolver:
    """Short-lived pronoun memory; expires on idle or explicit topic change."""

    def __init__(self, idle_seconds: int = 180) -> None:
        self.idle_seconds = idle_seconds
        self._entity: dict[str, Any] | None = None
        self._updated_at = 0.0

    def remember(self, entity: dict[str, Any]) -> None:
        self._entity = dict(entity)
        self._updated_at = time.monotonic()

    def resolve(self, phrase: str) -> dict[str, Any] | None:
        if time.monotonic() - self._updated_at > self.idle_seconds:
            self.clear()
            return None
        value = phrase.casefold().strip()
        if value in {"it", "that", "this", "that one", "the other one", "same one"}:
            return dict(self._entity) if self._entity else None
        return None

    def clear(self) -> None:
        self._entity = None
        self._updated_at = 0.0
