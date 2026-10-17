from __future__ import annotations

import math
from dataclasses import dataclass
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
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(vector) for vector in self._model.embed(texts)]


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
        examples = [
            (action.name, phrase)
            for action in registry.all()
            for phrase in (action.description, *action.examples)
        ]
        vectors = embedder.embed([phrase for _, phrase in examples])
        self._examples = [
            (name, phrase, vector)
            for (name, phrase), vector in zip(examples, vectors, strict=True)
        ]
        if self.store is not None:
            for row in self.store.semantic_examples():
                if self.registry.get(row["action_name"]) is not None:
                    self._examples.append((
                        row["action_name"], row["phrase"], row["vector"],
                    ))

    def retrieve(self, utterance: str, limit: int = 8) -> list[RetrievedAction]:
        vector = self.embedder.embed([utterance])[0]
        ranked = [
            RetrievedAction(action_name=name, score=cosine(vector, example_vector), example=phrase)
            for name, phrase, example_vector in self._examples
        ]
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:limit]

    def add_example(self, action_name: str, phrase: str, max_examples_per_action: int = 40) -> bool:
        if self.registry.get(action_name) is None:
            return False
        vector = self.embedder.embed([phrase])[0]
        existing = [row for row in self._examples if row[0] == action_name]
        if any(cosine(vector, row[2]) > 0.95 for row in existing):
            return False
        if len(existing) >= max_examples_per_action:
            weakest = min(existing, key=lambda row: len(row[1]))
            self._examples.remove(weakest)
            if self.store is not None:
                self.store.remove_semantic_example(action_name, weakest[1])
        self._examples.append((action_name, phrase, vector))
        if self.store is not None:
            self.store.add_semantic_example(action_name, phrase, vector)
        return True
