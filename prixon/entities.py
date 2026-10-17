from __future__ import annotations

import os
import time
from pathlib import Path
from difflib import SequenceMatcher
from typing import Any

from prixon.store import AgentStore
from prixon.embeddings import cosine


class EntityIndex:
    """Incremental index of grounded apps, processes, windows, files and settings."""

    def __init__(self, store: AgentStore, embedder=None) -> None:
        self.store = store
        self.embedder = embedder
        self._vectors: dict[tuple[str, str, str], list[float]] = {}

    def refresh(self, kind: str, entities: list[dict[str, Any]], source: str = "perception") -> int:
        count = 0
        missing_vectors: list[tuple[tuple[str, str, str], str]] = []
        for entity in entities:
            name, target = str(entity.get("name", "")).strip(), entity.get("target")
            if not name or not target:
                continue
            self.store.add_entity(kind, name, str(target), source, entity)
            if self.embedder is not None and kind in {"application", "window", "folder", "file", "setting"}:
                normalized = " ".join(name.casefold().split())
                key = (kind, normalized, str(target))
                if key not in self._vectors:
                    missing_vectors.append((key, name))
            count += 1
        if missing_vectors:
            vectors = self.embedder.embed([name for _, name in missing_vectors])
            self._vectors.update({
                key: vector for (key, _), vector in zip(missing_vectors, vectors, strict=True)
            })
        return count

    @staticmethod
    def _alias_target_exists(target_type: str, target: str) -> bool:
        if target_type == "application":
            path = Path(target).expanduser()
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                return False
            roots = [
                Path(os.environ.get("APPDATA", "C:/__missing__")) / "Microsoft/Windows/Start Menu/Programs",
                Path(os.environ.get("PROGRAMDATA", "C:/__missing__")) / "Microsoft/Windows/Start Menu/Programs",
                Path(os.environ.get("WINDIR", "C:/Windows")) / "System32",
            ]
            return resolved.is_file() and any(
                resolved == root.resolve() or root.resolve() in resolved.parents for root in roots
            )
        if target_type in {"file", "folder"}:
            path = Path(target).expanduser()
            try:
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError):
                return False
            home = Path.home().resolve()
            if resolved != home and home not in resolved.parents:
                return False
            return resolved.is_file() if target_type == "file" else resolved.is_dir()
        if target_type == "window":
            try:
                handle = int(target)
            except (TypeError, ValueError):
                return False
            if os.name != "nt":
                return True
            import ctypes
            return bool(ctypes.windll.user32.IsWindow(handle))
        if target_type == "setting":
            return target.startswith("ms-settings:")
        return bool(target)

    def resolve(
        self, mention: str, kind: str | None = None, threshold: float = 0.78,
        context_target: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        query = " ".join(mention.casefold().split())
        if not query:
            return None
        alias = self.store.alias(query)
        if alias and (kind is None or alias["target_type"] == kind):
            alias_scope = alias.get("scope") or {}
            scope_matches = all(
                (context or {}).get(key) == value for key, value in alias_scope.items()
            )
            target_exists = (
                any(
                    row["kind"] == alias["target_type"] and row["target"] == alias["target"]
                    for row in self.store.entity_rows(alias["target_type"])
                )
                or self._alias_target_exists(alias["target_type"], alias["target"])
            )
            if scope_matches and target_exists:
                return {
                    "kind": alias["target_type"],
                    "name": mention,
                    "target": alias["target"],
                    "score": alias["confidence"],
                    "matched_by": "owner_alias",
                }
            if not target_exists:
                self.store.audit("stale_entity_alias", {
                    "phrase": query, "target_type": alias["target_type"],
                    "target": alias["target"],
                })
        best: dict[str, Any] | None = None
        best_score = 0.0
        runner_up = 0.0
        entities = self.store.entity_rows(kind)
        query_vector = None
        if self.embedder is not None and kind in {"application", "window", "folder", "file", "setting"}:
            query_vector = self.embedder.embed([mention])[0]
        for entity in entities:
            name = entity["normalized"]
            fuzzy_score = 1.0 if query == name else SequenceMatcher(None, query, name).ratio()
            score = fuzzy_score
            if query_vector is not None:
                key = (entity["kind"], name, str(entity["target"]))
                vector = self._vectors.get(key)
                if vector is None:
                    vector = self.embedder.embed([entity["name"]])[0]
                    self._vectors[key] = vector
                semantic_score = cosine(query_vector, vector)
                score = (0.6 * semantic_score) + (0.4 * fuzzy_score)
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
            "score": best_score,
            "matched_by": "exact" if best_score == 1 else ("embedding_fuzzy" if query_vector is not None else "fuzzy"),
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
