from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass(slots=True)
class OddsClient:
    base_url: str
    api_key: str
    timeout: float = 30.0

    def get_premier_league_h2h(self) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url.rstrip('/')}/sports/soccer_epl/odds",
            params={
                "apiKey": self.api_key,
                "regions": "uk",
                "markets": "h2h",
                "oddsFormat": "decimal",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()