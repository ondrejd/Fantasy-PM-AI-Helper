from __future__ import annotations

from pathlib import Path

from fantasy_pl_ai_helper.storage.database import connect


def initialize_database(database_path: Path) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")

    with connect(database_path) as connection:
        connection.executescript(schema_sql)


def main() -> int:
    from fantasy_pl_ai_helper.config import get_settings

    settings = get_settings()
    initialize_database(settings.database_path)
    print(f"Database initialized at: {settings.database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
