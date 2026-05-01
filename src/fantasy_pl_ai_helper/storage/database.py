from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(database_path: Path | str) -> sqlite3.Connection:
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA busy_timeout = 30000;")
    connection.execute("PRAGMA journal_mode = WAL;")
    return connection
