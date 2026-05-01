import sqlite3

from fantasy_pl_ai_helper.models.projections import ProjectionModel


def _feat(**kwargs):
    base = {
        "player_id": 1,
        "fpl_player_id": 1,
        "team_id": 1,
        "opponent_team_id": 2,
        "full_name": "Test Player",
        "position": 3,
        "salary": 70,
        "availability_status": "a",
        "rolling_avg_fpts_5g": 10.0,
        "rolling_avg_fpts_10g": 10.0,
        "rolling_avg_xg_5g": None,
        "rolling_avg_xa_5g": None,
        "rolling_avg_xgc_5g": None,
        "games_in_window": 5,
        "injury_flag": 0,
        "chance_of_playing": 100,
        "fixture_difficulty": 3,
        "team_win_prob": 0.5,
        "has_fixture": 1,
    }
    base.update(kwargs)
    return base


def test_project_applies_chance_of_playing_multiplier():
    model = ProjectionModel(connection=sqlite3.connect(":memory:"), gameweek_id=1)
    fpts, notes = model._project(_feat(chance_of_playing=75))
    assert fpts == 7.5
    assert "availability=75% coeff=0.75" in notes


def test_project_zeroes_unavailable_status():
    model = ProjectionModel(connection=sqlite3.connect(":memory:"), gameweek_id=1)
    fpts, notes = model._project(_feat(availability_status="s", chance_of_playing=None))
    assert fpts == 0.0
    assert notes == "injured"