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


class LineupResponse(BaseModel):
    gameweek_id: int
    total_fpts: float
    total_salary: int
    total_salary_display: str
    slots: list[LineupSlotResponse]


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


class EvaluationReportResponse(BaseModel):
    rows: list[EvaluationReportItem]
