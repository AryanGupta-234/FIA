from __future__ import annotations

import httpx


class OllamaClient:
    """Small local Ollama HTTP client; never falls back to a hosted model."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:3b-instruct",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def health(self) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                payload = response.json()
            models = [
                item.get("name", "") for item in payload.get("models", [])
                if isinstance(item, dict)
            ]
            return {
                "available": True,
                "base_url": self.base_url,
                "configured_model": self.model,
                "model_present": self.model in models,
                "models": models,
                "mode": "local_only",
            }
        except (httpx.HTTPError, ValueError):
            return {
                "available": False,
                "base_url": self.base_url,
                "configured_model": self.model,
                "model_present": False,
                "models": [],
                "mode": "local_only",
                "error": "ollama_unavailable",
            }

    async def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "keep_alive": "10m",
            "options": {"temperature": 0, "num_predict": 256},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        import json

        content = data.get("message", {}).get("content", "")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Ollama response must be a JSON object")
        return parsed
