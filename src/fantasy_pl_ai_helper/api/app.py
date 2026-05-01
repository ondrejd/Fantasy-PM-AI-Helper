from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from fantasy_pl_ai_helper.api.contracts import (
    BackendWinnerTrendResponse,
    CurrentGameweekResponse,
    DataUpdateResponse,
    EvaluationReportResponse,
    EvaluationReportItem,
    EvaluationResponse,
    GameweekFixtureItemResponse,
    GameweekFixturesResponse,
    HealthResponse,
    LineupResponse,
    LineupSlotResponse,
    ProjectionItem,
    ProjectionsResponse,
    WinnerTimelineItemResponse,
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
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
            # Prefer the next gameweek for planning/recommendations.
            row = conn.execute(
                """
                SELECT id, fpl_event_id, name, deadline_time,
                       is_current, is_next, finished
                FROM gameweeks
                WHERE is_next = 1
                ORDER BY fpl_event_id ASC
                LIMIT 1
                """
            ).fetchone()

            if not row:
                row = conn.execute(
                    """
                    SELECT id, fpl_event_id, name, deadline_time,
                           is_current, is_next, finished
                    FROM gameweeks
                    WHERE is_current = 1
                    ORDER BY fpl_event_id ASC
                    LIMIT 1
                    """
                ).fetchone()

            if not row:
                row = conn.execute(
                    """
                    SELECT id, fpl_event_id, name, deadline_time,
                           is_current, is_next, finished
                    FROM gameweeks
                    WHERE finished = 0
                    ORDER BY fpl_event_id ASC
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

    @app.get("/v1/gameweeks/{gw_id}/fixtures", response_model=GameweekFixturesResponse)
    def gameweek_fixtures(gw_id: int) -> GameweekFixturesResponse:
        with get_conn() as conn:
            _assert_gameweek_exists(conn, gw_id)
            rows = conn.execute(
                """
                SELECT
                    f.id,
                    f.kickoff_time,
                    f.started,
                    f.finished,
                    f.home_score,
                    f.away_score,
                    ht.full_name AS home_team_name,
                    ht.short_name AS home_team_short_name,
                    ht.fpl_team_id AS home_team_fpl_id,
                    ht.logo_url AS home_team_logo_url,
                    at.full_name AS away_team_name,
                    at.short_name AS away_team_short_name,
                    at.fpl_team_id AS away_team_fpl_id,
                    at.logo_url AS away_team_logo_url
                FROM fixtures f
                JOIN teams ht ON ht.id = f.home_team_id
                JOIN teams at ON at.id = f.away_team_id
                WHERE f.gameweek_id = ?
                ORDER BY f.kickoff_time ASC, f.id ASC
                """,
                (gw_id,),
            ).fetchall()

        fixtures = [
            GameweekFixtureItemResponse(
                fixture_id=r["id"],
                kickoff_time=r["kickoff_time"],
                started=bool(r["started"]),
                finished=bool(r["finished"]),
                home_score=r["home_score"],
                away_score=r["away_score"],
                home_team_name=r["home_team_name"],
                home_team_short_name=r["home_team_short_name"],
                home_team_fpl_id=r["home_team_fpl_id"],
                home_team_logo_url=(
                    r["home_team_logo_url"]
                    or _default_team_logo_url(
                        r["home_team_fpl_id"],
                        team_name=r["home_team_name"],
                        team_short_name=r["home_team_short_name"],
                    )
                ),
                away_team_name=r["away_team_name"],
                away_team_short_name=r["away_team_short_name"],
                away_team_fpl_id=r["away_team_fpl_id"],
                away_team_logo_url=(
                    r["away_team_logo_url"]
                    or _default_team_logo_url(
                        r["away_team_fpl_id"],
                        team_name=r["away_team_name"],
                        team_short_name=r["away_team_short_name"],
                    )
                ),
            )
            for r in rows
        ]

        return GameweekFixturesResponse(
            gameweek_id=gw_id,
            count=len(fixtures),
            fixtures=fixtures,
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
                    team_name=s.get("team_name"),
                    team_short_name=s.get("team_short_name"),
                    team_fpl_id=s.get("team_fpl_id"),
                    team_logo_url=s.get("team_logo_url"),
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
    def evaluations_report(
        rows: int = Query(default=10, ge=1, le=100),
        primary_winner_metric: str = Query(default="mae", pattern="^(mae|lineup_delta_abs)$"),
        from_gameweek: int | None = Query(default=None, ge=1, le=38),
        to_gameweek: int | None = Query(default=None, ge=1, le=38),
    ) -> EvaluationReportResponse:
        with get_conn() as conn:
            # Use a dummy gameweek_id; report() doesn't filter by it
            evaluator = ProjectionEvaluator(connection=conn, gameweek_id=0)
            report = evaluator.report(
                days=rows,
                model_artifact_path=settings.model_artifact_path,
                primary_winner_metric=primary_winner_metric,
                from_gameweek=from_gameweek,
                to_gameweek=to_gameweek,
            )
            report_rows = report["rows"]
            trend_mae = report.get("backend_winner_trend_mae")
            trend_lineup_delta = report.get("backend_winner_trend_lineup_delta")
            winner_timeline = report.get("winner_timeline") or []
        return EvaluationReportResponse(
            primary_winner_metric=report.get("primary_winner_metric", primary_winner_metric),
            applied_from_gameweek=from_gameweek,
            applied_to_gameweek=to_gameweek,
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
                    backend_winner=r.get("backend_winner"),
                    backend_winner_mae=r.get("backend_winner_mae"),
                    backend_winner_lineup_delta=r.get("backend_winner_lineup_delta"),
                )
                for r in report_rows
            ],
            backend_winner_trend_mae=(
                BackendWinnerTrendResponse(**trend_mae) if trend_mae is not None else None
            ),
            backend_winner_trend_lineup_delta=(
                BackendWinnerTrendResponse(**trend_lineup_delta)
                if trend_lineup_delta is not None
                else None
            ),
            winner_timeline=[
                WinnerTimelineItemResponse(**item)
                for item in winner_timeline
            ],
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
            p.team_id,
            t.full_name AS team_name,
            t.short_name AS team_short_name,
            t.fpl_team_id AS team_fpl_id,
            t.logo_url AS team_logo_url,
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
        LEFT JOIN teams t ON t.id = p.team_id
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
        team_name=p.get("team_name"),
        team_short_name=p.get("team_short_name"),
        team_fpl_id=p.get("team_fpl_id"),
        team_logo_url=(
            p.get("team_logo_url")
            or _default_team_logo_url(
                p.get("team_fpl_id"),
                team_name=p.get("team_name"),
                team_short_name=p.get("team_short_name"),
            )
        ),
    )


def _default_team_logo_url(
    fpl_team_id: int | None,
    team_name: str | None = None,
    team_short_name: str | None = None,
) -> str | None:
    """Build a robust PL badge URL.

    FPL team_id and PL badge code are not always identical, so resolve by
    known team names/short names when possible and only then fall back.
    """

    name_to_badge_code = {
        "arsenal": 3,
        "aston villa": 7,
        "avl": 7,
        "bournemouth": 91,
        "bou": 91,
        "brentford": 94,
        "bre": 94,
        "brighton": 36,
        "brighton and hove albion": 36,
        "bha": 36,
        "burnley": 90,
        "bur": 90,
        "chelsea": 8,
        "crystal palace": 31,
        "cry": 31,
        "everton": 11,
        "fulham": 54,
        "ful": 54,
        "ipswich": 40,
        "ipswich town": 40,
        "ips": 40,
        "leicester": 13,
        "leicester city": 13,
        "lei": 13,
        "liverpool": 14,
        "man city": 43,
        "manchester city": 43,
        "mci": 43,
        "man utd": 1,
        "manchester united": 1,
        "mun": 1,
        "newcastle": 4,
        "newcastle united": 4,
        "new": 4,
        "nott'm forest": 17,
        "nottingham forest": 17,
        "nfo": 17,
        "southampton": 20,
        "sou": 20,
        "tottenham": 6,
        "tottenham hotspur": 6,
        "spurs": 6,
        "tot": 6,
        "west ham": 21,
        "west ham united": 21,
        "whu": 21,
        "wolves": 39,
        "wolverhampton": 39,
        "wolverhampton wanderers": 39,
        "wol": 39,
    }

    badge_code: int | None = None
    if team_name:
        badge_code = name_to_badge_code.get(team_name.strip().lower())
    if badge_code is None and team_short_name:
        badge_code = name_to_badge_code.get(team_short_name.strip().lower())
    if badge_code is None:
        badge_code = fpl_team_id

    if not badge_code:
        return None
    return f"https://resources.premierleague.com/premierleague/badges/70/t{badge_code}.png"


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
