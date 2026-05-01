from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests


class OllamaError(Exception):
    pass


@dataclass(slots=True)
class OllamaClient:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "llama3.1:8b"
    timeout_seconds: float = 120.0

    def chat(self, system: str, user: str) -> str:
        url = f"{self.base_url.rstrip('/')}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout_seconds)
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"]
        except requests.RequestException as exc:
            raise OllamaError(str(exc)) from exc
