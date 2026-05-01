from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database: str


class DataUpdateResponse(BaseModel):
    teams: int
    players: int
    gameweeks: int
    fixtures: int
    game_logs: int


class CurrentGameweekResponse(BaseModel):
    gameweek_id: int
    fpl_event_id: int
    name: str
    deadline_time: str | None
    is_current: bool
    is_next: bool
    finished: bool


class ProjectionItem(BaseModel):
    player_id: int
    fpl_player_id: int
    full_name: str
    position: int
    position_name: str
    salary: int
    salary_display: str
    projected_fpts: float
    rolling_avg_fpts_5g: float | None
    rolling_avg_fpts_10g: float | None
    injury_flag: bool
    fixture_difficulty: float | None
    team_win_prob: float | None
    notes: str
    team_name: str | None
    team_short_name: str | None
    team_fpl_id: int | None
    team_logo_url: str | None


class ProjectionsResponse(BaseModel):
    gameweek_id: int
    count: int
    players: list[ProjectionItem]


class LineupSlotResponse(BaseModel):
    slot: str
    player_id: int
    fpl_player_id: int
    full_name: str
    position: int
    position_name: str
    salary: int
    salary_display: str
    projected_fpts: float
    team_name: str | None
    team_short_name: str | None
    team_fpl_id: int | None
    team_logo_url: str | None


class LineupResponse(BaseModel):
    gameweek_id: int
    total_fpts: float
    total_salary: int
    total_salary_display: str
    slots: list[LineupSlotResponse]


class GameweekFixtureItemResponse(BaseModel):
    fixture_id: int
    kickoff_time: str | None
    started: bool
    finished: bool
    home_score: int | None
    away_score: int | None
    home_team_name: str
    home_team_short_name: str | None
    home_team_fpl_id: int
    home_team_logo_url: str | None
    away_team_name: str
    away_team_short_name: str | None
    away_team_fpl_id: int
    away_team_logo_url: str | None


class GameweekFixturesResponse(BaseModel):
    gameweek_id: int
    count: int
    fixtures: list[GameweekFixtureItemResponse]


class EvaluationResponse(BaseModel):
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


class EvaluationReportItem(BaseModel):
    gameweek_id: int
    gw_name: str
    evaluated_players: int
    mae: float | None
    rmse: float | None
    bias: float | None
    lineup_delta_actual_fpts: float | None
    missing_history_rate: float | None
    backend_winner: str | None
    backend_winner_mae: str | None
    backend_winner_lineup_delta: str | None


class BackendWinnerTrendResponse(BaseModel):
    metric: str
    compared_gameweeks: int
    baseline_wins: int
    ml_wins: int
    ties: int
    baseline_win_rate: float | None
    ml_win_rate: float | None


class WinnerTimelineItemResponse(BaseModel):
    gameweek_id: int
    gw_name: str
    winner_mae: str | None
    winner_lineup_delta: str | None
    winner_primary: str | None
    baseline_mae: float | None
    ml_mae: float | None
    baseline_lineup_delta_abs: float | None
    ml_lineup_delta_abs: float | None


class EvaluationReportResponse(BaseModel):
    primary_winner_metric: str
    applied_from_gameweek: int | None
    applied_to_gameweek: int | None
    rows: list[EvaluationReportItem]
    backend_winner_trend_mae: BackendWinnerTrendResponse | None
    backend_winner_trend_lineup_delta: BackendWinnerTrendResponse | None
    winner_timeline: list[WinnerTimelineItemResponse]
