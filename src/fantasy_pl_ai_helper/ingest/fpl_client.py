from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass(slots=True)
class FplClient:
    """Thin HTTP client for the official Fantasy Premier League API."""

    base_url: str = "https://fantasy.premierleague.com/api"
    timeout: float = 30.0
    _session: requests.Session = field(default_factory=requests.Session, init=False, repr=False)

    def __post_init__(self) -> None:
        self._session.headers.update(
            {
                "User-Agent": "fantasy-pl-ai-helper/0.1 (github.com/ondrejd/fantasy-pm-ai-helper)",
                "Accept": "application/json",
            }
        )

    def get_bootstrap(self) -> dict[str, Any]:
        """Return /bootstrap-static/ — teams, players (elements), events."""
        return self._get("/bootstrap-static/")

    def get_fixtures(self, event: int | None = None) -> list[dict[str, Any]]:
        """Return fixtures, optionally filtered to a single gameweek."""
        params = {"event": event} if event is not None else {}
        return self._get("/fixtures/", params=params)  # type: ignore[return-value]

    def get_element_summary(self, player_id: int) -> dict[str, Any]:
        """Return /element-summary/{player_id}/ — player history + upcoming fixtures."""
        return self._get(f"/element-summary/{player_id}/")

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = self.base_url.rstrip("/") + path
        resp = self._session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()
