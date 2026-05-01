from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    project_root: Path
    database_path: Path
    fpl_api_base_url: str
    http_timeout_seconds: float
    odds_api_base_url: str
    odds_api_key: str | None
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    projection_backend: str
    model_artifact_path: Path
    # FPL budget cap in £0.1M units (1000 = £100M)
    salary_cap: int
    cors_origins: list[str]
    cors_origin_regex: str

    @classmethod
    def from_root(cls, project_root: Path) -> "Settings":
        data_dir = project_root / "data"
        cors_origins_raw = os.getenv("FANTASY_PL_CORS_ORIGINS", "")
        cors_origins = [
            origin.strip()
            for origin in cors_origins_raw.split(",")
            if origin.strip()
        ]
        return cls(
            project_root=project_root,
            database_path=data_dir / "fantasy_pl.sqlite3",
            fpl_api_base_url="https://fantasy.premierleague.com/api",
            http_timeout_seconds=30.0,
            odds_api_base_url=os.getenv("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4"),
            odds_api_key=os.getenv("ODDS_API_KEY"),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1:8b"),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "600")),
            projection_backend=os.getenv("FANTASY_PL_PROJECTION_BACKEND", "baseline"),
            model_artifact_path=(data_dir / "models" / "latest.pkl"),
            salary_cap=1000,  # £100M in 0.1M units
            cors_origins=cors_origins,
            cors_origin_regex=os.getenv(
                "FANTASY_PL_CORS_ORIGIN_REGEX",
                r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
            ),
        )


def get_settings() -> Settings:
    project_root_env = os.getenv("FANTASY_PL_PROJECT_ROOT")
    database_path_env = os.getenv("FANTASY_PL_DATABASE_PATH")

    if project_root_env:
        project_root = Path(project_root_env).expanduser().resolve()
    else:
        cwd = Path.cwd().resolve()
        if (cwd / "pyproject.toml").exists() and (cwd / "src").exists():
            project_root = cwd
        else:
            project_root = Path(__file__).resolve().parents[2]

    settings = Settings.from_root(project_root)
    if database_path_env:
        settings.database_path = Path(database_path_env).expanduser().resolve()
        settings.model_artifact_path = settings.database_path.parent / "models" / "latest.pkl"
    return settings
