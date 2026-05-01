from pathlib import Path

from fantasy_pl_ai_helper.models.ml import MLModelArtifact


def test_ml_artifact_missing_file_raises(tmp_path):
    missing = tmp_path / "missing.pkl"
    try:
        MLModelArtifact.load(missing)
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("Expected FileNotFoundError")