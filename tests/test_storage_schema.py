import sqlite3
import pytest

from fantasy_pl_ai_helper.storage.init_db import initialize_database


def test_initialize_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    initialize_database(str(db_path))

    conn = sqlite3.connect(str(db_path))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    expected = {
        "seasons", "teams", "players", "gameweeks", "fixtures",
        "player_game_logs", "player_projections", "projection_evaluations", "injuries",
    }
    assert expected.issubset(tables)
