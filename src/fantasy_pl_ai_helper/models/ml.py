from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection
from typing import TypedDict

from sklearn.ensemble import HistGradientBoostingRegressor

from fantasy_pl_ai_helper.features.pipeline import FeaturePipeline, PlayerFeatures
from fantasy_pl_ai_helper.scoring.engine import ScoringEngine


class TrainingSummary(TypedDict):
    model_path: str
    trained_at: str
    sample_count: int
    gameweek_count: int
    feature_count: int
    target_mean: float


FEATURE_NAMES = [
    "position_gk",
    "position_def",
    "position_mid",
    "position_fwd",
    "salary",
    "rolling_avg_fpts_5g",
    "rolling_avg_fpts_10g",
    "rolling_avg_xg_5g",
    "rolling_avg_xa_5g",
    "rolling_avg_xgc_5g",
    "games_in_window",
    "injury_flag",
    "chance_of_playing",
    "fixture_difficulty",
    "team_win_prob",
    "has_fixture",
]


@dataclass(slots=True)
class MLModelArtifact:
    estimator: object
    model_name: str
    feature_names: list[str]
    trained_at: str
    sample_count: int
    gameweek_count: int

    def predict(self, feat: PlayerFeatures) -> float:
        row = [_feature_vector(feat)]
        prediction = self.estimator.predict(row)[0]
        return float(prediction)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            pickle.dump(
                {
                    "estimator": self.estimator,
                    "model_name": self.model_name,
                    "feature_names": self.feature_names,
                    "trained_at": self.trained_at,
                    "sample_count": self.sample_count,
                    "gameweek_count": self.gameweek_count,
                },
                handle,
            )

    @classmethod
    def load(cls, path: Path | str) -> "MLModelArtifact":
        artifact_path = Path(path)
        if not artifact_path.exists():
            raise FileNotFoundError(f"ML model artifact not found: {artifact_path}")
        with artifact_path.open("rb") as handle:
            payload = pickle.load(handle)
        return cls(
            estimator=payload["estimator"],
            model_name=payload["model_name"],
            feature_names=list(payload["feature_names"]),
            trained_at=payload["trained_at"],
            sample_count=int(payload["sample_count"]),
            gameweek_count=int(payload["gameweek_count"]),
        )


@dataclass(slots=True)
class MLProjectionTrainer:
    connection: Connection
    scoring_engine: ScoringEngine = field(default_factory=ScoringEngine)
    window_long: int = 10
    window_short: int = 5

    def train(self, output_path: Path | str, upto_gameweek_id: int | None = None) -> TrainingSummary:
        rows, targets, gameweek_count = self._build_training_set(upto_gameweek_id)
        if len(rows) < 50:
            raise ValueError(f"Not enough training samples: {len(rows)}")

        estimator = HistGradientBoostingRegressor(
            random_state=42,
            max_depth=4,
            learning_rate=0.05,
            max_iter=200,
            min_samples_leaf=10,
        )
        estimator.fit(rows, targets)

        trained_at = datetime.now(UTC).isoformat()
        artifact = MLModelArtifact(
            estimator=estimator,
            model_name="hist_gradient_boosting",
            feature_names=list(FEATURE_NAMES),
            trained_at=trained_at,
            sample_count=len(rows),
            gameweek_count=gameweek_count,
        )
        artifact_path = Path(output_path)
        artifact.save(artifact_path)

        return TrainingSummary(
            model_path=str(artifact_path),
            trained_at=trained_at,
            sample_count=len(rows),
            gameweek_count=gameweek_count,
            feature_count=len(FEATURE_NAMES),
            target_mean=round(sum(targets) / len(targets), 4),
        )

    def _build_training_set(self, upto_gameweek_id: int | None) -> tuple[list[list[float]], list[float], int]:
        query = "SELECT id FROM gameweeks WHERE finished = 1"
        params: list[object] = []
        if upto_gameweek_id is not None:
            query += " AND id < ?"
            params.append(upto_gameweek_id)
        query += " ORDER BY id ASC"

        gameweek_rows = self.connection.execute(query, params).fetchall()
        rows: list[list[float]] = []
        targets: list[float] = []
        used_gameweeks = 0

        for gw_row in gameweek_rows:
            gw_id = int(gw_row[0])
            from fantasy_pl_ai_helper.models.projections import load_feature_snapshots

            features = load_feature_snapshots(self.connection, gw_id)
            if not features:
                features = FeaturePipeline(
                    connection=self.connection,
                    gameweek_id=gw_id,
                    scoring_engine=self.scoring_engine,
                    window_long=self.window_long,
                    window_short=self.window_short,
                    include_finished_fixtures=True,
                ).build()
            if not features:
                continue

            actual_by_player = self._actual_fpts_by_player(gw_id)
            added_for_gw = 0
            for feat in features:
                actual = actual_by_player.get(int(feat["player_id"]))
                if actual is None:
                    continue
                rows.append(_feature_vector(feat))
                targets.append(float(actual))
                added_for_gw += 1

            if added_for_gw:
                used_gameweeks += 1

        return rows, targets, used_gameweeks

    def _actual_fpts_by_player(self, gameweek_id: int) -> dict[int, float]:
        query = """
            SELECT pgl.player_id, p.position,
                   pgl.minutes, pgl.goals_scored, pgl.assists, pgl.clean_sheets,
                   pgl.goals_conceded, pgl.own_goals, pgl.penalties_saved,
                   pgl.penalties_missed, pgl.yellow_cards, pgl.red_cards,
                   pgl.saves, pgl.result_type
            FROM player_game_logs pgl
            JOIN fixtures f ON f.id = pgl.fixture_id
            JOIN players p ON p.id = pgl.player_id
            WHERE f.gameweek_id = ?
              AND f.finished = 1
        """
        rows = self.connection.execute(query, (gameweek_id,)).fetchall()
        result: dict[int, float] = {}
        for row in rows:
            scored = self.scoring_engine.score_game_log(dict(row), position=int(row["position"]))
            player_id = int(row["player_id"])
            result[player_id] = result.get(player_id, 0.0) + scored
        return result


def _feature_vector(feat: PlayerFeatures) -> list[float]:
    position = int(feat["position"])
    chance = feat.get("chance_of_playing")
    return [
        1.0 if position == 1 else 0.0,
        1.0 if position == 2 else 0.0,
        1.0 if position == 3 else 0.0,
        1.0 if position == 4 else 0.0,
        float(feat["salary"]),
        float(feat.get("rolling_avg_fpts_5g") or 0.0),
        float(feat.get("rolling_avg_fpts_10g") or 0.0),
        float(feat.get("rolling_avg_xg_5g") or 0.0),
        float(feat.get("rolling_avg_xa_5g") or 0.0),
        float(feat.get("rolling_avg_xgc_5g") or 0.0),
        float(feat.get("games_in_window") or 0),
        float(feat.get("injury_flag") or 0),
        float(100 if chance is None else chance),
        float(feat.get("fixture_difficulty") or 3),
        float(feat.get("team_win_prob") or 0.5),
        float(feat.get("has_fixture") or 0),
    ]