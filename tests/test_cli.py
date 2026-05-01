import pytest
from fantasy_pl_ai_helper.cli.main import build_parser


def test_build_parser_returns_parser():
    parser = build_parser()
    assert parser is not None


def test_update_data_command():
    parser = build_parser()
    args = parser.parse_args(["update-data"])
    assert args.command == "update-data"


def test_rebuild_projections_default_gameweek():
    parser = build_parser()
    args = parser.parse_args(["rebuild-projections"])
    assert args.command == "rebuild-projections"
    assert args.gameweek is None


def test_rebuild_projections_with_gameweek():
    parser = build_parser()
    args = parser.parse_args(["rebuild-projections", "--gameweek", "28"])
    assert args.gameweek == 28


def test_rebuild_projections_with_backend():
    parser = build_parser()
    args = parser.parse_args(["rebuild-projections", "--backend", "ml", "--ml-model-path", "model.pkl"])
    assert args.backend == "ml"
    assert args.ml_model_path == "model.pkl"


def test_recommend_lineup_defaults():
    parser = build_parser()
    args = parser.parse_args(["recommend-lineup"])
    assert args.command == "recommend-lineup"
    assert args.exclude == []
    assert args.lock == []


def test_recommend_lineup_with_exclude_and_lock():
    parser = build_parser()
    args = parser.parse_args(["recommend-lineup", "--exclude", "5", "10", "--lock", "3"])
    assert args.exclude == [5, 10]
    assert args.lock == [3]


def test_ask_ai_question():
    parser = build_parser()
    args = parser.parse_args(["ask-ai", "Kdo bude nejlepší hráč?"])
    assert args.command == "ask-ai"
    assert "nejlepší" in args.question


def test_evaluate_report_rows_default():
    parser = build_parser()
    args = parser.parse_args(["evaluate-report"])
    assert args.rows == 10


def test_evaluate_report_rows_custom():
    parser = build_parser()
    args = parser.parse_args(["evaluate-report", "--rows", "5"])
    assert args.rows == 5


def test_train_ml_model_defaults():
    parser = build_parser()
    args = parser.parse_args(["train-ml-model"])
    assert args.command == "train-ml-model"
    assert args.upto_gameweek is None
    assert args.output is None


def test_recommend_lineup_with_ml_backend():
    parser = build_parser()
    args = parser.parse_args(["recommend-lineup", "--backend", "ml", "--ml-model-path", "foo.pkl"])
    assert args.backend == "ml"
    assert args.ml_model_path == "foo.pkl"
