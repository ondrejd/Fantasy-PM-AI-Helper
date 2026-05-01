import sqlite3
import pytest

from fantasy_pl_ai_helper.optimizer.lineup import LineupOptimizer, GK, DEF, MID, FWD


def _proj(player_id, position, salary, fpts, name=None):
    return {
        "player_id": player_id,
        "fpl_player_id": player_id,
        "team_id": 1,
        "opponent_team_id": 2,
        "full_name": name or f"Player {player_id}",
        "position": position,
        "salary": salary,
        "projected_fpts": fpts,
        "rolling_avg_fpts_5g": fpts,
        "rolling_avg_fpts_10g": fpts,
        "games_in_window": 5,
        "injury_flag": 0,
        "chance_of_playing": 100,
        "fixture_difficulty": 3,
        "team_win_prob": 0.5,
        "notes": "",
    }


def _make_pool():
    """Make a basic pool with 3 GK, 8 DEF, 8 MID, 6 FWD."""
    players = []
    pid = 1
    for _ in range(3):
        players.append(_proj(pid, GK, 50, 6.0))
        pid += 1
    for i in range(8):
        players.append(_proj(pid, DEF, 55, 5.0 + i * 0.1))
        pid += 1
    for i in range(8):
        players.append(_proj(pid, MID, 65, 6.0 + i * 0.1))
        pid += 1
    for i in range(6):
        players.append(_proj(pid, FWD, 80, 7.0 + i * 0.1))
        pid += 1
    return players


def test_optimize_returns_11_players():
    pool = _make_pool()
    optimizer = LineupOptimizer(gameweek_id=1, salary_cap=1000)
    lineup = optimizer.optimize(pool)
    assert lineup is not None
    assert len(lineup["slots"]) == 11


def test_optimize_has_exactly_one_gk():
    pool = _make_pool()
    optimizer = LineupOptimizer(gameweek_id=1, salary_cap=1000)
    lineup = optimizer.optimize(pool)
    gk_count = sum(1 for s in lineup["slots"] if s["position"] == GK)
    assert gk_count == 1


def test_optimize_salary_within_cap():
    pool = _make_pool()
    cap = 1000
    optimizer = LineupOptimizer(gameweek_id=1, salary_cap=cap)
    lineup = optimizer.optimize(pool)
    assert lineup["total_salary"] <= cap


def test_optimize_returns_none_when_not_enough_players():
    # Only 1 GK and not enough outfield
    pool = [
        _proj(1, GK, 50, 6.0),
        _proj(2, DEF, 55, 5.0),
        _proj(3, MID, 65, 6.0),
    ]
    optimizer = LineupOptimizer(gameweek_id=1, salary_cap=1000)
    lineup = optimizer.optimize(pool)
    assert lineup is None


def test_optimize_respects_excluded_players():
    pool = _make_pool()
    # Best GK is player_id=1 — exclude him
    optimizer = LineupOptimizer(
        gameweek_id=1, salary_cap=1000, excluded_player_ids={1}
    )
    lineup = optimizer.optimize(pool)
    assert lineup is not None
    player_ids = {s["player_id"] for s in lineup["slots"]}
    assert 1 not in player_ids


def test_optimize_tight_budget_still_finds_lineup():
    # Make all players expensive so we need budget fitting
    pool = _make_pool()
    # Raise salaries to close to cap
    for p in pool:
        p["salary"] = 85  # 11 * 85 = 935 — under 1000
    optimizer = LineupOptimizer(gameweek_id=1, salary_cap=1000)
    lineup = optimizer.optimize(pool)
    assert lineup is not None
    assert lineup["total_salary"] <= 1000


def test_optimize_impossible_budget_returns_none():
    pool = _make_pool()
    for p in pool:
        p["salary"] = 200  # impossible
    optimizer = LineupOptimizer(gameweek_id=1, salary_cap=1000)
    lineup = optimizer.optimize(pool)
    assert lineup is None
