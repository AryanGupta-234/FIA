from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from prixon.registry import ActionRegistry


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedAdapter:
    """Optional BGE embeddings. Install the semantic extra and prewarm the model locally."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "Semantic retrieval requires installing the optional semantic dependency."
            ) from exc
        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        # Keep peak memory low on CPU-class Windows laptops.
        for start in range(0, len(texts), 256):
            batch = texts[start:start + 256]
            vectors.extend(list(vector) for vector in self._model.embed(batch))
        return vectors


def cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


@dataclass(frozen=True)
class RetrievedAction:
    action_name: str
    score: float
    example: str


class SemanticRetriever:
    def __init__(self, registry: ActionRegistry, embedder: Embedder, store=None) -> None:
        self.registry = registry
        self.embedder = embedder
        self.store = store
        examples: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add_example(action_name: str, phrase: str) -> None:
            key = (action_name, phrase.casefold().strip())
            if key not in seen:
                seen.add(key)
                examples.append((action_name, phrase))

        for action in registry.all():
            add_example(action.name, action.description)
            for phrase in action.examples:
                add_example(action.name, phrase)

        seed_path = Path(__file__).parent / "data" / "global_seed_v1.jsonl"
        if seed_path.exists():
            with seed_path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    action_name = str(row.get("action_name") or "")
                    phrase = str(row.get("text") or "").strip()
                    if phrase and registry.get(action_name) is not None:
                        add_example(action_name, phrase)
        self.global_seed_count = len(examples)

        self._examples: list[tuple[str, str, list[float]]] = []
        self._user_example_keys: set[tuple[str, str]] = set()
        model_name = str(getattr(embedder, "model_name", type(embedder).__name__))
        corpus_version = "global_seed_v1"
        cached = (
            self.store.cached_seed_embeddings(model_name, corpus_version)
            if self.store is not None else {}
        )
        missing: list[tuple[str, str]] = []
        for action_name, phrase in examples:
            vector = cached.get((action_name, phrase))
            if vector is None:
                missing.append((action_name, phrase))
            else:
                self._examples.append((action_name, phrase, vector))
        self.seed_embedding_cache_hits = len(examples) - len(missing)
        self.seed_embedding_cache_misses = len(missing)

        batch_size = 256
        for start in range(0, len(missing), batch_size):
            batch = missing[start:start + batch_size]
            vectors = embedder.embed([phrase for _, phrase in batch])
            encoded = [
                (name, phrase, vector)
                for (name, phrase), vector in zip(batch, vectors, strict=True)
            ]
            self._examples.extend(encoded)
            if self.store is not None:
                self.store.cache_seed_embeddings(model_name, corpus_version, encoded)

        if self.store is not None:
            for row in self.store.semantic_examples():
                action_name = row["action_name"]
                phrase = row["phrase"]
                key = (action_name, phrase.casefold().strip())
                if self.registry.get(action_name) is None or key in seen:
                    continue
                self._examples.append((action_name, phrase, row["vector"]))
                self._user_example_keys.add(key)

    def clear_user_examples(self) -> int:
        user_rows = self.store.semantic_examples() if self.store is not None else []
        for row in user_rows:
            key = (row["action_name"], row["phrase"].casefold().strip())
            self._examples = [
                item for item in self._examples
                if not (item[0] == row["action_name"] and item[1] == row["phrase"])
            ]
            self._user_example_keys.discard(key)
            if self.store is not None:
                self.store.remove_semantic_example(row["action_name"], row["phrase"])
        return len(user_rows)

    def retrieve(self, utterance: str, limit: int = 8) -> list[RetrievedAction]:
        vector = self.embedder.embed([utterance])[0]
        best_by_action: dict[str, RetrievedAction] = {}
        for name, phrase, example_vector in self._examples:
            score = cosine(vector, example_vector)
            previous = best_by_action.get(name)
            if previous is None or score > previous.score:
                best_by_action[name] = RetrievedAction(
                    action_name=name, score=score, example=phrase,
                )
        ranked = sorted(best_by_action.values(), key=lambda item: item.score, reverse=True)
        return ranked[:limit]

    def add_example(self, action_name: str, phrase: str, max_examples_per_action: int = 40) -> bool:
        if self.registry.get(action_name) is None:
            return False
        vector = self.embedder.embed([phrase])[0]
        existing = [row for row in self._examples if row[0] == action_name]
        if any(cosine(vector, row[2]) > 0.95 for row in existing):
            return False
        user_rows = [
            row for row in self._examples
            if row[0] == action_name and (row[0], row[1].casefold().strip()) in self._user_example_keys
        ]
        if len(user_rows) >= max_examples_per_action:
            weakest = min(user_rows, key=lambda row: len(row[1]))
            self._examples.remove(weakest)
            self._user_example_keys.discard((weakest[0], weakest[1].casefold().strip()))
            if self.store is not None:
                self.store.remove_semantic_example(action_name, weakest[1])
        self._examples.append((action_name, phrase, vector))
        self._user_example_keys.add((action_name, phrase.casefold().strip()))
        if self.store is not None:
            self.store.add_semantic_example(action_name, phrase, vector)
        return True
