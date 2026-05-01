import pytest
from fantasy_pl_ai_helper.scoring.engine import ScoringEngine

GK, DEF, MID, FWD = 1, 2, 3, 4


@pytest.fixture
def engine():
    return ScoringEngine()


def _log(**kwargs):
    defaults = dict(
        goals_scored=0, assists=0, clean_sheets=0, goals_conceded=0,
        saves=0, penalties_saved=0, penalties_missed=0,
        yellow_cards=0, red_cards=0, own_goals=0,
        minutes=90, result_type="W",
        expected_goals=0.0, expected_assists=0.0, expected_goals_conceded=0.0,
    )
    defaults.update(kwargs)
    return defaults


# ------------------------------------------------------------------
# Minutes
# ------------------------------------------------------------------

def test_minutes_90_gives_4_points(engine):
    row = _log(minutes=90, result_type="W")
    pts = engine.score_game_log(row, FWD)
    # 90 // 20 = 4 minute points + 2 win = 6
    assert pts >= 4


def test_minutes_0_gives_0_minute_points(engine):
    row = _log(minutes=0, result_type=None)
    pts = engine.score_game_log(row, FWD)
    assert pts == 0


# ------------------------------------------------------------------
# Goals
# ------------------------------------------------------------------

def test_fwd_goal_scores_12(engine):
    row = _log(goals_scored=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, FWD)
    assert pts == 12


def test_mid_goal_scores_18(engine):
    row = _log(goals_scored=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, MID)
    assert pts == 18


def test_def_goal_scores_24(engine):
    row = _log(goals_scored=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, DEF)
    assert pts == 24


def test_gk_goal_scores_30(engine):
    row = _log(goals_scored=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, GK)
    assert pts == 30


# ------------------------------------------------------------------
# Assists
# ------------------------------------------------------------------

def test_fwd_assist_scores_6(engine):
    row = _log(assists=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, FWD)
    assert pts == 6


def test_gk_assist_scores_15(engine):
    row = _log(assists=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, GK)
    assert pts == 15


# ------------------------------------------------------------------
# Clean sheet
# ------------------------------------------------------------------

def test_gk_clean_sheet_scores_3(engine):
    row = _log(clean_sheets=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, GK)
    assert pts == 3


def test_def_clean_sheet_scores_2(engine):
    row = _log(clean_sheets=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, DEF)
    assert pts == 2


# ------------------------------------------------------------------
# GK extras
# ------------------------------------------------------------------

def test_gk_save_scores_3_each(engine):
    row = _log(saves=3, result_type=None, minutes=0)
    pts = engine.score_game_log(row, GK)
    assert pts == 9


def test_gk_penalty_saved_scores_8(engine):
    row = _log(penalties_saved=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, GK)
    assert pts == 8


def test_gk_goals_conceded_minus_3_each(engine):
    row = _log(goals_conceded=2, result_type=None, minutes=0)
    pts = engine.score_game_log(row, GK)
    assert pts == -6


# ------------------------------------------------------------------
# Cards
# ------------------------------------------------------------------

def test_yellow_card_fwd_minus_4(engine):
    # FWD yellow card = -4 per scoring engine
    row = _log(yellow_cards=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, FWD)
    assert pts == -4


def test_red_card_fwd_minus_10(engine):
    # FWD red card = -10 per scoring engine
    row = _log(red_cards=1, result_type=None, minutes=0)
    pts = engine.score_game_log(row, FWD)
    assert pts == -10


# ------------------------------------------------------------------
# Win / draw / loss
# ------------------------------------------------------------------

def test_win_gives_plus_2(engine):
    row = _log(result_type="W", minutes=0)
    pts = engine.score_game_log(row, FWD)
    assert pts == 2


def test_draw_gives_plus_1(engine):
    row = _log(result_type="D", minutes=0)
    pts = engine.score_game_log(row, FWD)
    assert pts == 1


def test_loss_gives_minus_2(engine):
    row = _log(result_type="L", minutes=0)
    pts = engine.score_game_log(row, FWD)
    assert pts == -2
