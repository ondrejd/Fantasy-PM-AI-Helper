from __future__ import annotations

from dataclasses import dataclass, field
from sqlite3 import Connection
from typing import TypedDict

from fantasy_pl_ai_helper.scoring.engine import ScoringEngine


class PlayerFeatures(TypedDict):
    player_id: int
    fpl_player_id: int
    team_id: int
    opponent_team_id: int | None
    full_name: str
    position: int          # 1=GK, 2=DEF, 3=MID, 4=FWD
    salary: int            # now_cost in £0.1M units
    availability_status: str | None
    # Rolling averages of custom fantasy points
    rolling_avg_fpts_5g: float | None
    rolling_avg_fpts_10g: float | None
    # xStats rolling averages
    rolling_avg_xg_5g: float | None
    rolling_avg_xa_5g: float | None
    rolling_avg_xgc_5g: float | None
    games_in_window: int
    injury_flag: int
    chance_of_playing: int | None  # 0-100 or None
    fixture_difficulty: int | None  # 1-5, 1=easiest
    team_win_prob: float | None
    has_fixture: int       # 1 if has a gameweek fixture


@dataclass(slots=True)
class FeaturePipeline:
    """Builds per-player feature rows for a given gameweek.

    Usage::

        pipeline = FeaturePipeline(connection, gameweek_id=35)
        rows = pipeline.build()
    """

    connection: Connection
    gameweek_id: int
    scoring_engine: ScoringEngine = field(default_factory=ScoringEngine)
    window_long: int = 10
    window_short: int = 5
    include_finished_fixtures: bool = False
    history_cutoff_time: str | None = None

    def build(self) -> list[PlayerFeatures]:
        fixtures = self._fixtures_in_gw()
        if not fixtures:
            return []

        home_team_ids = {f["home_team_id"] for f in fixtures}
        away_team_ids = {f["away_team_id"] for f in fixtures}
        playing_teams = home_team_ids | away_team_ids

        # Build fixture lookup: team_id → fixture info
        team_fixture: dict[int, dict] = {}
        for f in fixtures:
            team_fixture[f["home_team_id"]] = {
                "fixture_id": f["id"],
                "opponent_team_id": f["away_team_id"],
                "was_home": 1,
                "difficulty": f.get("home_difficulty"),
            }
            team_fixture[f["away_team_id"]] = {
                "fixture_id": f["id"],
                "opponent_team_id": f["home_team_id"],
                "was_home": 0,
                "difficulty": f.get("away_difficulty"),
            }

        # Injured / unavailable players
        injured_ids = self._injured_player_ids()

        # Team strength / win probabilities
        team_win_probs = self._compute_win_probs(fixtures)

        # All active players in playing teams
        players = self._players_in_teams(playing_teams)

        results: list[PlayerFeatures] = []
        for p in players:
            player_id = p["id"]
            team_id = p["team_id"]
            position = p["position"]

            fx = team_fixture.get(team_id)
            if not fx:
                continue  # team has no fixture this GW

            cutoff_time = self.history_cutoff_time or _history_cutoff(fixtures)
            logs = self._recent_logs(player_id, self.window_long, cutoff_time=cutoff_time)
            fpts_list: list[float] = []
            for log in logs:
                scored = self.scoring_engine.score_game_log(
                    dict(log), position=position
                )
                fpts_list.append(scored)

            # Rolling averages
            avg5 = _mean(fpts_list[: self.window_short]) if fpts_list else None
            avg10 = _mean(fpts_list) if fpts_list else None
            games_in_window = len(fpts_list)

            # xStats rolling averages (short window)
            xg_5g = _stat_mean(logs, "expected_goals", self.window_short)
            xa_5g = _stat_mean(logs, "expected_assists", self.window_short)
            xgc_5g = _stat_mean(logs, "expected_goals_conceded", self.window_short)

            injury_flag = 1 if player_id in injured_ids else 0
            chance = p.get("chance_of_playing_next_round")

            results.append(
                PlayerFeatures(
                    player_id=player_id,
                    fpl_player_id=p["fpl_player_id"],
                    team_id=team_id,
                    opponent_team_id=fx["opponent_team_id"],
                    full_name=p["full_name"],
                    position=position,
                    salary=p["now_cost"],
                    availability_status=p.get("status"),
                    rolling_avg_fpts_5g=avg5,
                    rolling_avg_fpts_10g=avg10,
                    rolling_avg_xg_5g=xg_5g,
                    rolling_avg_xa_5g=xa_5g,
                    rolling_avg_xgc_5g=xgc_5g,
                    games_in_window=games_in_window,
                    injury_flag=injury_flag,
                    chance_of_playing=chance,
                    fixture_difficulty=fx["difficulty"],
                    team_win_prob=team_win_probs.get(team_id),
                    has_fixture=1,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fixtures_in_gw(self) -> list[dict]:
        query = """
            SELECT id, home_team_id, away_team_id,
                   home_difficulty, away_difficulty, kickoff_time
            FROM fixtures
            WHERE gameweek_id = ?
        """
        if not self.include_finished_fixtures:
            query += "\n              AND finished = 0"
        rows = self.connection.execute(query, (self.gameweek_id,)).fetchall()
        return [dict(r) for r in rows]

    def _players_in_teams(self, team_ids: set[int]) -> list[dict]:
        if not team_ids:
            return []
        placeholders = ",".join("?" * len(team_ids))
        rows = self.connection.execute(
            f"""
            SELECT id, fpl_player_id, full_name, position, team_id,
                   now_cost, status, chance_of_playing_next_round
            FROM players
            WHERE team_id IN ({placeholders})
              AND is_active = 1
            """,
            list(team_ids),
        ).fetchall()
        return [dict(r) for r in rows]

    def _recent_logs(self, player_id: int, n: int, cutoff_time: str | None = None) -> list[dict]:
        query = """
            SELECT pgl.*
            FROM player_game_logs pgl
            JOIN fixtures f ON f.id = pgl.fixture_id
            WHERE pgl.player_id = ?
              AND f.finished = 1
        """
        params: list[object] = [player_id]
        if cutoff_time is not None:
            query += "\n              AND f.kickoff_time < ?"
            params.append(cutoff_time)
        query += "\n            ORDER BY f.kickoff_time DESC\n            LIMIT ?"
        params.append(n)
        rows = self.connection.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def _injured_player_ids(self) -> set[int]:
        rows = self.connection.execute(
            """
            SELECT player_id FROM injuries
            WHERE is_active = 1
              AND (injury_status IN ('i', 's') OR chance_of_playing_next_round = 0)
            """
        ).fetchall()
        return {int(r[0]) for r in rows}

    def _compute_win_probs(self, fixtures: list[dict]) -> dict[int, float]:
        """Use stored betting odds when available, else fallback to team strengths."""
        result: dict[int, float] = {}
        for f in fixtures:
            h_id = f["home_team_id"]
            a_id = f["away_team_id"]

            odds_row = self.connection.execute(
                """
                SELECT home_win_prob, away_win_prob
                FROM fixture_odds
                WHERE fixture_id = ?
                ORDER BY fetched_at DESC
                LIMIT 1
                """,
                (f["id"],),
            ).fetchone()
            if odds_row and odds_row["home_win_prob"] is not None and odds_row["away_win_prob"] is not None:
                result[h_id] = round(float(odds_row["home_win_prob"]), 4)
                result[a_id] = round(float(odds_row["away_win_prob"]), 4)
                continue

            h_row = self.connection.execute(
                "SELECT strength_overall_home, strength_overall_away FROM teams WHERE id = ?",
                (h_id,),
            ).fetchone()
            a_row = self.connection.execute(
                "SELECT strength_overall_home, strength_overall_away FROM teams WHERE id = ?",
                (a_id,),
            ).fetchone()

            if not h_row or not a_row:
                result[h_id] = 0.5
                result[a_id] = 0.5
                continue

            h_str = float(h_row[0] or 1000)
            a_str = float(a_row[1] or 1000)  # away strength (attacking vs away)

            # Logistic model: home advantage ~+50 rating points
            diff = (h_str + 50) - a_str
            h_win_prob = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))

            result[h_id] = round(h_win_prob, 4)
            result[a_id] = round(1.0 - h_win_prob, 4)

        return result


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _stat_mean(logs: list[dict], key: str, window: int) -> float | None:
    vals = []
    for log in logs[:window]:
        v = log.get(key)
        if v is not None:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
    return _mean(vals) if vals else None


def _history_cutoff(fixtures: list[dict]) -> str | None:
    kickoff_times = [f.get("kickoff_time") for f in fixtures if f.get("kickoff_time")]
    if not kickoff_times:
        return None
    return min(kickoff_times)
