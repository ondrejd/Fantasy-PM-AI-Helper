from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query

from fantasy_pl_ai_helper.api.contracts import (
    CurrentGameweekResponse,
    DataUpdateResponse,
    EvaluationReportResponse,
    EvaluationReportItem,
    EvaluationResponse,
    HealthResponse,
    LineupResponse,
    LineupSlotResponse,
    ProjectionItem,
    ProjectionsResponse,
)
from fantasy_pl_ai_helper.config import Settings, get_settings
from fantasy_pl_ai_helper.ingest.service import IngestService
from fantasy_pl_ai_helper.models.evaluation import ProjectionEvaluator
from fantasy_pl_ai_helper.models.projections import ProjectionModel
from fantasy_pl_ai_helper.optimizer.lineup import LineupOptimizer, POSITION_NAMES
from fantasy_pl_ai_helper.storage.database import connect
from fantasy_pl_ai_helper.storage.init_db import initialize_database


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = get_settings()

    initialize_database(settings.database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        yield

    app = FastAPI(
        title="Fantasy PL AI Helper",
        version="0.1.0",
        lifespan=lifespan,
    )

    def get_conn() -> sqlite3.Connection:
        return connect(settings.database_path)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", database=str(settings.database_path))

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    @app.post("/v1/data/update", response_model=DataUpdateResponse)
    def data_update() -> DataUpdateResponse:
        stats = IngestService(settings=settings).run()
        return DataUpdateResponse(
            teams=stats.get("teams", 0),
            players=stats.get("players", 0),
            gameweeks=stats.get("gameweeks", 0),
            fixtures=stats.get("fixtures", 0),
            game_logs=stats.get("game_logs", 0),
        )

    # ------------------------------------------------------------------
    # Gameweeks
    # ------------------------------------------------------------------

    @app.get("/v1/gameweeks/current", response_model=CurrentGameweekResponse)
    def gameweeks_current() -> CurrentGameweekResponse:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT id, fpl_event_id, name, deadline_time,
                       is_current, is_next, finished
                FROM gameweeks
                WHERE is_current = 1 OR is_next = 1
                ORDER BY is_current DESC, id ASC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No current/next gameweek found.")
        return CurrentGameweekResponse(
            gameweek_id=row["id"],
            fpl_event_id=row["fpl_event_id"],
            name=row["name"],
            deadline_time=row["deadline_time"],
            is_current=bool(row["is_current"]),
            is_next=bool(row["is_next"]),
            finished=bool(row["finished"]),
        )

    # ------------------------------------------------------------------
    # Projections
    # ------------------------------------------------------------------

    @app.get("/v1/gameweeks/{gw_id}/projections", response_model=ProjectionsResponse)
    def gameweek_projections(
        gw_id: int,
        rebuild: bool = Query(default=False),
        top: int = Query(default=50, ge=1, le=500),
    ) -> ProjectionsResponse:
        with get_conn() as conn:
            _assert_gameweek_exists(conn, gw_id)
            if rebuild:
                projections = ProjectionModel(connection=conn, gameweek_id=gw_id).build()
            else:
                projections = _load_projections(conn, gw_id)

        projections = sorted(projections, key=lambda p: p["projected_fpts"], reverse=True)[:top]
        items = [_projection_to_item(p) for p in projections]
        return ProjectionsResponse(gameweek_id=gw_id, count=len(items), players=items)

    # ------------------------------------------------------------------
    # Lineup
    # ------------------------------------------------------------------

    @app.get("/v1/gameweeks/{gw_id}/lineup", response_model=LineupResponse)
    def gameweek_lineup(
        gw_id: int,
        exclude: list[int] = Query(default=[]),
        lock: list[int] = Query(default=[]),
    ) -> LineupResponse:
        with get_conn() as conn:
            _assert_gameweek_exists(conn, gw_id)
            projections = _load_projections(conn, gw_id)

        if not projections:
            raise HTTPException(
                status_code=404,
                detail=f"No projections for gameweek {gw_id}. Call ?rebuild=true on /projections first.",
            )

        optimizer = LineupOptimizer(
            gameweek_id=gw_id,
            excluded_player_ids=set(exclude),
            locked_player_ids=set(lock),
        )
        lineup = optimizer.optimize(projections)
        if lineup is None:
            raise HTTPException(status_code=422, detail="Cannot build a valid lineup within constraints.")

        return LineupResponse(
            gameweek_id=lineup["gameweek_id"],
            total_fpts=lineup["total_fpts"],
            total_salary=lineup["total_salary"],
            total_salary_display=f"£{lineup['total_salary'] / 10:.1f}M",
            slots=[
                LineupSlotResponse(
                    slot=s["slot"],
                    player_id=s["player_id"],
                    fpl_player_id=s["fpl_player_id"],
                    full_name=s["full_name"],
                    position=s["position"],
                    position_name=POSITION_NAMES.get(s["position"], "?"),
                    salary=s["salary"],
                    salary_display=f"£{s['salary'] / 10:.1f}M",
                    projected_fpts=s["projected_fpts"],
                )
                for s in lineup["slots"]
            ],
        )

    # ------------------------------------------------------------------
    # Evaluate
    # ------------------------------------------------------------------

    @app.post("/v1/gameweeks/{gw_id}/evaluate", response_model=EvaluationResponse)
    def gameweek_evaluate(gw_id: int) -> EvaluationResponse:
        with get_conn() as conn:
            _assert_gameweek_exists(conn, gw_id)
            summary = ProjectionEvaluator(connection=conn, gameweek_id=gw_id).evaluate()
        return EvaluationResponse(
            gameweek_id=gw_id,
            backend=summary["backend"],
            evaluated_players=summary["evaluated_players"],
            mae=summary["mae"],
            rmse=summary["rmse"],
            bias=summary["bias"],
            lineup_delta_actual_fpts=summary["lineup_delta_actual_fpts"],
            missing_history_players=summary["missing_history_players"],
            missing_history_rate=summary["missing_history_rate"],
            backend_comparisons=summary["backend_comparisons"],
        )

    @app.get("/v1/evaluations/report", response_model=EvaluationReportResponse)
    def evaluations_report(rows: int = Query(default=10, ge=1, le=100)) -> EvaluationReportResponse:
        with get_conn() as conn:
            # Use a dummy gameweek_id; report() doesn't filter by it
            evaluator = ProjectionEvaluator(connection=conn, gameweek_id=0)
            report_rows = evaluator.report(days=rows)
        return EvaluationReportResponse(
            rows=[
                EvaluationReportItem(
                    gameweek_id=r["gameweek_id"],
                    gw_name=r["gw_name"],
                    evaluated_players=r["evaluated_players"],
                    mae=r["mae"],
                    rmse=r["rmse"],
                    bias=r["bias"],
                    lineup_delta_actual_fpts=r.get("lineup_delta_actual_fpts"),
                    missing_history_rate=r.get("missing_history_rate"),
                )
                for r in report_rows
            ]
        )

    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_gameweek_exists(conn: sqlite3.Connection, gw_id: int) -> None:
    row = conn.execute("SELECT id FROM gameweeks WHERE id = ?", (gw_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Gameweek {gw_id} not found.")


def _load_projections(conn: sqlite3.Connection, gw_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT
            pp.player_id,
            p.fpl_player_id,
            p.full_name,
            pp.position,
            pp.salary,
            pp.projected_fpts,
            pp.rolling_avg_fpts_5g,
            pp.rolling_avg_fpts_10g,
            pp.injury_flag,
            pp.fixture_difficulty,
            pp.team_win_prob,
            pp.notes
        FROM player_projections pp
        JOIN players p ON p.id = pp.player_id
        WHERE pp.gameweek_id = ?
        """,
        (gw_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _projection_to_item(p: dict) -> ProjectionItem:
    return ProjectionItem(
        player_id=p["player_id"],
        fpl_player_id=p["fpl_player_id"],
        full_name=p["full_name"],
        position=p["position"],
        position_name=POSITION_NAMES.get(p["position"], "?"),
        salary=p["salary"],
        salary_display=f"£{p['salary'] / 10:.1f}M",
        projected_fpts=p["projected_fpts"],
        rolling_avg_fpts_5g=p.get("rolling_avg_fpts_5g"),
        rolling_avg_fpts_10g=p.get("rolling_avg_fpts_10g"),
        injury_flag=bool(p.get("injury_flag")),
        fixture_difficulty=p.get("fixture_difficulty"),
        team_win_prob=p.get("team_win_prob"),
        notes=p.get("notes") or "",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    settings = get_settings()
    uvicorn.run(
        "fantasy_pl_ai_helper.api.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
