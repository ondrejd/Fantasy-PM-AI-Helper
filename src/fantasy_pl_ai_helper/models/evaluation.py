from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import Connection
from typing import TypedDict

from fantasy_pl_ai_helper.features.pipeline import FeaturePipeline
from fantasy_pl_ai_helper.models.ml import MLModelArtifact
from fantasy_pl_ai_helper.models.projections import ProjectionModel, load_feature_snapshots
from fantasy_pl_ai_helper.optimizer.lineup import LineupOptimizer
from fantasy_pl_ai_helper.scoring.engine import ScoringEngine


class EvaluationSummary(TypedDict):
    gameweek_id: int
    backend: str
    evaluated_players: int
    mae: float | None
    rmse: float | None
    bias: float | None
    lineup_delta_actual_fpts: float | None
    missing_history_players: int
    missing_history_rate: float | None
    backend_comparisons: list[dict]


class BackendComparison(TypedDict):
    backend: str
    evaluated_players: int
    mae: float | None
    rmse: float | None
    bias: float | None
    lineup_delta_actual_fpts: float | None


@dataclass(slots=True)
class ProjectionEvaluator:
    """Evaluate stored projections against realized GW outcomes."""

    connection: Connection
    gameweek_id: int
    scoring_engine: ScoringEngine = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.scoring_engine is None:
            self.scoring_engine = ScoringEngine()

    def evaluate(self, model_artifact_path: Path | str | None = None) -> EvaluationSummary:
        self._ensure_schema()

        actual_by_player = self._actual_fpts_by_player()
        proj_rows = self.connection.execute(
            """
            SELECT pp.id, pp.player_id, pp.position, pp.projected_fpts,
                     pp.backend, pp.rolling_avg_fpts_5g, pp.games_in_window, pp.injury_flag, pp.notes,
                     pp.salary, p.fpl_player_id, p.full_name
            FROM player_projections pp
            JOIN players p ON p.id = pp.player_id
            WHERE pp.gameweek_id = ?
            """,
            (self.gameweek_id,),
        ).fetchall()

        if not proj_rows:
            backend_comparisons = self._compare_backends(actual_by_player, model_artifact_path)
            return EvaluationSummary(
                gameweek_id=self.gameweek_id,
                backend="unknown",
                evaluated_players=0,
                mae=None, rmse=None, bias=None,
                lineup_delta_actual_fpts=None,
                missing_history_players=0,
                missing_history_rate=None,
                backend_comparisons=backend_comparisons,
            )

        errors: list[float] = []
        sq_errors: list[float] = []
        biases: list[float] = []
        missing_history = 0

        for row in proj_rows:
            pid = int(row["player_id"])
            proj = float(row["projected_fpts"])
            actual = actual_by_player.get(pid, 0.0)
            err = abs(actual - proj)
            errors.append(err)
            sq_errors.append(err ** 2)
            biases.append(actual - proj)
            if row["games_in_window"] == 0:
                missing_history += 1

            # Update projection row with actual
            self.connection.execute(
                """
                UPDATE player_projections
                SET actual_fpts=?, abs_error=?, sq_error=?, evaluated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (actual, err, err ** 2, int(row["id"])),
            )

        n = len(errors)
        mae = sum(errors) / n if n else None
        rmse = math.sqrt(sum(sq_errors) / n) if n else None
        bias = sum(biases) / n if n else None
        missing_rate = missing_history / n if n else None
        lineup_delta = self._lineup_delta_actual_fpts(proj_rows, actual_by_player)
        backend = str(proj_rows[0]["backend"] or "baseline")
        backend_comparisons = self._compare_backends(actual_by_player, model_artifact_path)

        self.connection.execute(
            """
            INSERT INTO projection_evaluations (
                gameweek_id, evaluated_players, mae, rmse, bias,
                missing_history_players, missing_history_rate
                , lineup_delta_actual_fpts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.gameweek_id, n, mae, rmse, bias, missing_history, missing_rate, lineup_delta),
        )
        self.connection.commit()

        return EvaluationSummary(
            gameweek_id=self.gameweek_id,
            backend=backend,
            evaluated_players=n,
            mae=mae,
            rmse=rmse,
            bias=bias,
            lineup_delta_actual_fpts=lineup_delta,
            missing_history_players=missing_history,
            missing_history_rate=missing_rate,
            backend_comparisons=backend_comparisons,
        )

    def report(self, days: int = 10) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT pe.gameweek_id, gw.name AS gw_name,
                   pe.evaluated_players, pe.mae, pe.rmse, pe.bias,
                     pe.lineup_delta_actual_fpts, pe.missing_history_rate, pe.created_at
            FROM projection_evaluations pe
            JOIN gameweeks gw ON gw.id = pe.gameweek_id
            ORDER BY pe.created_at DESC
            LIMIT ?
            """,
            (days,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _actual_fpts_by_player(self) -> dict[int, float]:
        rows = self.connection.execute(
            """
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
            """,
            (self.gameweek_id,),
        ).fetchall()

        result: dict[int, float] = {}
        for row in rows:
            scored = self.scoring_engine.score_game_log(dict(row), position=int(row["position"]))
            pid = int(row["player_id"])
            result[pid] = result.get(pid, 0.0) + scored
        return result

    def _lineup_delta_actual_fpts(
        self,
        proj_rows: list,
        actual_by_player: dict[int, float],
    ) -> float | None:
        projected_pool = [self._row_to_optimizer_player(row, float(row["projected_fpts"])) for row in proj_rows]
        actual_pool = [
            self._row_to_optimizer_player(row, actual_by_player.get(int(row["player_id"]), 0.0))
            for row in proj_rows
        ]

        optimizer = LineupOptimizer(gameweek_id=self.gameweek_id)
        projected_lineup = optimizer.optimize(projected_pool)
        actual_lineup = optimizer.optimize(actual_pool)
        if projected_lineup is None or actual_lineup is None:
            return None

        projected_actual_total = sum(
            actual_by_player.get(int(slot["player_id"]), 0.0)
            for slot in projected_lineup["slots"]
        )
        return round(projected_actual_total - float(actual_lineup["total_fpts"]), 4)

    def _compare_backends(
        self,
        actual_by_player: dict[int, float],
        model_artifact_path: Path | str | None,
    ) -> list[BackendComparison]:
        features = load_feature_snapshots(self.connection, self.gameweek_id)
        if not features:
            features = FeaturePipeline(
                connection=self.connection,
                gameweek_id=self.gameweek_id,
                scoring_engine=self.scoring_engine,
                include_finished_fixtures=True,
            ).build()
        if not features:
            return []

        comparisons: list[BackendComparison] = []
        for backend_name in ("baseline", "ml"):
            artifact_path = Path(model_artifact_path) if model_artifact_path is not None else None
            if backend_name == "ml":
                if artifact_path is None:
                    continue
                try:
                    MLModelArtifact.load(artifact_path)
                except FileNotFoundError:
                    continue
            projections = ProjectionModel(
                connection=self.connection,
                gameweek_id=self.gameweek_id,
                backend=backend_name,
                model_artifact_path=artifact_path,
            ).project_features(features, persist=False)
            comparisons.append(self._summarize_backend(backend_name, projections, actual_by_player))
        return comparisons

    def _summarize_backend(
        self,
        backend_name: str,
        projections: list[dict],
        actual_by_player: dict[int, float],
    ) -> BackendComparison:
        errors: list[float] = []
        sq_errors: list[float] = []
        biases: list[float] = []
        for projection in projections:
            actual = actual_by_player.get(int(projection["player_id"]), 0.0)
            err = abs(actual - float(projection["projected_fpts"]))
            errors.append(err)
            sq_errors.append(err ** 2)
            biases.append(actual - float(projection["projected_fpts"]))

        n = len(errors)
        mae = sum(errors) / n if n else None
        rmse = math.sqrt(sum(sq_errors) / n) if n else None
        bias = sum(biases) / n if n else None

        lineup = LineupOptimizer(gameweek_id=self.gameweek_id).optimize(projections)
        actual_pool = [
            self._row_to_optimizer_player(projection, actual_by_player.get(int(projection["player_id"]), 0.0))
            for projection in projections
        ]
        actual_lineup = LineupOptimizer(gameweek_id=self.gameweek_id).optimize(actual_pool)
        lineup_delta = None
        if lineup is not None and actual_lineup is not None:
            projected_actual_total = sum(
                actual_by_player.get(int(slot["player_id"]), 0.0)
                for slot in lineup["slots"]
            )
            lineup_delta = round(projected_actual_total - float(actual_lineup["total_fpts"]), 4)

        return BackendComparison(
            backend=backend_name,
            evaluated_players=n,
            mae=mae,
            rmse=rmse,
            bias=bias,
            lineup_delta_actual_fpts=lineup_delta,
        )

    def _row_to_optimizer_player(self, row, fpts: float) -> dict:
        return {
            "player_id": int(row["player_id"]),
            "fpl_player_id": int(row["fpl_player_id"]),
            "team_id": None,
            "opponent_team_id": None,
            "full_name": row["full_name"],
            "position": int(row["position"]),
            "salary": int(row["salary"]),
            "projected_fpts": float(fpts),
            "rolling_avg_fpts_5g": row["rolling_avg_fpts_5g"],
            "rolling_avg_fpts_10g": None,
            "games_in_window": int(row["games_in_window"]),
            "injury_flag": int(row["injury_flag"]),
            "chance_of_playing": None,
            "fixture_difficulty": None,
            "team_win_prob": None,
            "notes": row["notes"] or "",
        }

    def _ensure_schema(self) -> None:
        cols = {
            r[1]
            for r in self.connection.execute(
                "PRAGMA table_info(player_projections)"
            ).fetchall()
        }
        for col, typ in [
            ("actual_fpts", "REAL"),
            ("abs_error", "REAL"),
            ("sq_error", "REAL"),
            ("evaluated_at", "TEXT"),
        ]:
            if col not in cols:
                self.connection.execute(
                    f"ALTER TABLE player_projections ADD COLUMN {col} {typ}"
                )
