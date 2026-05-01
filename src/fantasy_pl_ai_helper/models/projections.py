from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection
from typing import TypedDict

from fantasy_pl_ai_helper.features.pipeline import FeaturePipeline, PlayerFeatures


class PlayerProjection(TypedDict):
    player_id: int
    fpl_player_id: int
    team_id: int | None
    opponent_team_id: int | None
    full_name: str
    backend: str
    position: int          # 1=GK, 2=DEF, 3=MID, 4=FWD
    salary: int            # £0.1M units
    projected_fpts: float
    rolling_avg_fpts_5g: float | None
    rolling_avg_fpts_10g: float | None
    games_in_window: int
    injury_flag: int
    chance_of_playing: int | None
    fixture_difficulty: int | None
    team_win_prob: float | None
    notes: str


# Fallback expected fantasy points when no history is available
_FALLBACK_FPTS: dict[int, float] = {
    1: 6.0,   # GK
    2: 5.0,   # DEF
    3: 5.5,   # MID
    4: 6.0,   # FWD
}

# Blend weights: short-window more responsive to recent form
_WEIGHT_5G = 0.65
_WEIGHT_10G = 0.35

_UNAVAILABLE_STATUSES = {"i", "s", "u", "n"}


@dataclass(slots=True)
class ProjectionModel:
    """Deterministic baseline projection model for Fantasy Premier League.

    Computes *projected_fpts* as a weighted blend of the 5-game and 10-game
    rolling averages of custom fantasy points, adjusted for:

    * **injury_flag** → projection set to 0
    * **chance_of_playing < 50** → projection set to 0
    * **fixture_difficulty** → difficulty multiplier (1=easy → +10%, 5=hard → -10%)
    * **team_win_prob** → win probability coefficient
    """

    connection: Connection
    gameweek_id: int
    backend: str = "baseline"
    model_artifact_path: Path | None = None

    def build(self) -> list[PlayerProjection]:
        """Build projections for all eligible players in the gameweek."""
        _ensure_projection_schema(self.connection)
        pipeline = FeaturePipeline(
            connection=self.connection,
            gameweek_id=self.gameweek_id,
        )
        features = pipeline.build()

        built_at = datetime.now(UTC).isoformat()
        self._persist_feature_snapshots(features, built_at)
        return self.project_features(features, persist=True, built_at=built_at)

    def project_features(
        self,
        features: list[PlayerFeatures],
        persist: bool = False,
        built_at: str | None = None,
    ) -> list[PlayerProjection]:
        """Project already-built feature rows, optionally persisting them."""

        projections: list[PlayerProjection] = []
        built_at = built_at or datetime.now(UTC).isoformat()
        ml_artifact = self._load_ml_artifact() if self.backend == "ml" else None

        for feat in features:
            if self.backend == "ml":
                fpts, notes = self._project_ml(feat, ml_artifact)
            else:
                fpts, notes = self._project_baseline(feat)
            projections.append(
                PlayerProjection(
                    player_id=feat["player_id"],
                    fpl_player_id=feat["fpl_player_id"],
                    team_id=feat["team_id"],
                    opponent_team_id=feat["opponent_team_id"],
                    full_name=feat["full_name"],
                    backend=self.backend,
                    position=feat["position"],
                    salary=feat["salary"],
                    projected_fpts=fpts,
                    rolling_avg_fpts_5g=feat["rolling_avg_fpts_5g"],
                    rolling_avg_fpts_10g=feat["rolling_avg_fpts_10g"],
                    games_in_window=feat["games_in_window"],
                    injury_flag=feat["injury_flag"],
                    chance_of_playing=feat["chance_of_playing"],
                    fixture_difficulty=feat["fixture_difficulty"],
                    team_win_prob=feat["team_win_prob"],
                    notes=notes,
                )
            )

        if persist:
            self._persist(projections, built_at)
        return projections

    # ------------------------------------------------------------------
    # Projection formula
    # ------------------------------------------------------------------

    def _project_baseline(self, feat: PlayerFeatures) -> tuple[float, str]:
        notes_parts: list[str] = []

        # Hard zeros
        status = (feat.get("availability_status") or "").lower()
        if feat["injury_flag"] or status in _UNAVAILABLE_STATUSES:
            return 0.0, "injured"
        chance = feat.get("chance_of_playing")

        avg5 = feat["rolling_avg_fpts_5g"]
        avg10 = feat["rolling_avg_fpts_10g"]

        if avg5 is not None and avg10 is not None:
            base = _WEIGHT_5G * avg5 + _WEIGHT_10G * avg10
            notes_parts.append(f"avg5={avg5:.1f} avg10={avg10:.1f}")
        elif avg5 is not None:
            base = avg5
            notes_parts.append(f"avg5={avg5:.1f}")
        elif avg10 is not None:
            base = avg10
            notes_parts.append(f"avg10={avg10:.1f}")
        else:
            base = _FALLBACK_FPTS.get(feat["position"], 5.0)
            notes_parts.append(f"fallback={base:.1f}")

        # Fixture difficulty adjustment: 1=easy (+10%), 3=neutral (0%), 5=hard (-10%)
        diff = feat.get("fixture_difficulty")
        if diff is not None:
            diff_coeff = 1.0 + (3 - diff) * 0.05  # maps 1→+10%, 3→0%, 5→-10%
            base *= diff_coeff
            notes_parts.append(f"diff={diff} coeff={diff_coeff:.2f}")

        # Win probability coefficient — position-specific scaling so that
        # at win_prob=0.5 the coefficient is always 1.0 (neutral), while
        # wins/losses have a larger effect on defenders/keepers (clean sheets)
        # than on forwards (who can still score in a losing team).
        #   position: (base_at_0, scale)  →  coeff = base + scale * win_prob
        #   GK  (1): 0→0.50, 0.5→1.00, 1.0→1.50  (±50%)
        #   DEF (2): 0→0.55, 0.5→1.00, 1.0→1.45  (±45%)
        #   MID (3): 0→0.60, 0.5→1.00, 1.0→1.40  (±40%)
        #   FWD (4): 0→0.65, 0.5→1.00, 1.0→1.35  (±35%)
        _WIN_PROB_PARAMS = {1: (0.50, 1.00), 2: (0.55, 0.90), 3: (0.60, 0.80), 4: (0.65, 0.70)}
        win_prob = feat.get("team_win_prob")
        if win_prob is not None:
            pos = feat.get("position", 3)
            wp_base, wp_scale = _WIN_PROB_PARAMS.get(pos, (0.60, 0.80))
            win_coeff = wp_base + wp_scale * win_prob
            base *= win_coeff
            notes_parts.append(f"win_prob={win_prob:.2f} wcoeff={win_coeff:.2f}")

        availability_coeff, availability_note = _availability_adjustment(status, chance)
        if availability_coeff <= 0.0:
            return 0.0, availability_note
        if availability_coeff < 1.0:
            base *= availability_coeff
            notes_parts.append(availability_note)

        return round(max(0.0, base), 4), "; ".join(notes_parts)

    def _project(self, feat: PlayerFeatures) -> tuple[float, str]:
        return self._project_baseline(feat)

    def _project_ml(
        self,
        feat: PlayerFeatures,
        artifact,
    ) -> tuple[float, str]:
        if artifact is None:
            raise FileNotFoundError("ML backend requested but no model artifact is configured.")

        status = (feat.get("availability_status") or "").lower()
        if feat["injury_flag"] or status in _UNAVAILABLE_STATUSES:
            return 0.0, "injured"

        prediction = artifact.predict(feat)
        chance = feat.get("chance_of_playing")
        availability_coeff, availability_note = _availability_adjustment(status, chance)
        if availability_coeff <= 0.0:
            return 0.0, availability_note
        if availability_coeff < 1.0:
            prediction *= availability_coeff
            return round(max(0.0, prediction), 4), f"ml={artifact.model_name}; {availability_note}"
        return round(max(0.0, prediction), 4), f"ml={artifact.model_name}"

    def _load_ml_artifact(self):
        from fantasy_pl_ai_helper.models.ml import MLModelArtifact

        if self.model_artifact_path is None:
            raise FileNotFoundError("Missing ML model path.")
        return MLModelArtifact.load(self.model_artifact_path)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, projections: list[PlayerProjection], built_at: str) -> None:
        self.connection.execute(
            "DELETE FROM player_projections WHERE gameweek_id = ?",
            (self.gameweek_id,),
        )
        for p in projections:
            self.connection.execute(
                """
                INSERT INTO player_projections (
                    player_id, gameweek_id, backend, position, salary,
                    projected_fpts, rolling_avg_fpts_5g, rolling_avg_fpts_10g,
                    games_in_window, injury_flag, fixture_difficulty, team_win_prob,
                    notes, built_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, gameweek_id) DO UPDATE SET
                    backend=excluded.backend,
                    position=excluded.position,
                    salary=excluded.salary,
                    projected_fpts=excluded.projected_fpts,
                    rolling_avg_fpts_5g=excluded.rolling_avg_fpts_5g,
                    rolling_avg_fpts_10g=excluded.rolling_avg_fpts_10g,
                    games_in_window=excluded.games_in_window,
                    injury_flag=excluded.injury_flag,
                    fixture_difficulty=excluded.fixture_difficulty,
                    team_win_prob=excluded.team_win_prob,
                    notes=excluded.notes,
                    built_at=excluded.built_at
                """,
                (
                    p["player_id"],
                    self.gameweek_id,
                    p["backend"],
                    p["position"],
                    p["salary"],
                    p["projected_fpts"],
                    p["rolling_avg_fpts_5g"],
                    p["rolling_avg_fpts_10g"],
                    p["games_in_window"],
                    p["injury_flag"],
                    p["fixture_difficulty"],
                    p["team_win_prob"],
                    p["notes"],
                    built_at,
                ),
            )
        self.connection.commit()

    def _persist_feature_snapshots(self, features: list[PlayerFeatures], built_at: str) -> None:
        for feat in features:
            self.connection.execute(
                """
                INSERT INTO player_feature_snapshots (
                    player_id, gameweek_id, fpl_player_id, team_id, opponent_team_id,
                    full_name, position, salary, availability_status,
                    rolling_avg_fpts_5g, rolling_avg_fpts_10g,
                    rolling_avg_xg_5g, rolling_avg_xa_5g, rolling_avg_xgc_5g,
                    games_in_window, injury_flag, chance_of_playing,
                    fixture_difficulty, team_win_prob, has_fixture, snapshot_built_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, gameweek_id) DO UPDATE SET
                    fpl_player_id=excluded.fpl_player_id,
                    team_id=excluded.team_id,
                    opponent_team_id=excluded.opponent_team_id,
                    full_name=excluded.full_name,
                    position=excluded.position,
                    salary=excluded.salary,
                    availability_status=excluded.availability_status,
                    rolling_avg_fpts_5g=excluded.rolling_avg_fpts_5g,
                    rolling_avg_fpts_10g=excluded.rolling_avg_fpts_10g,
                    rolling_avg_xg_5g=excluded.rolling_avg_xg_5g,
                    rolling_avg_xa_5g=excluded.rolling_avg_xa_5g,
                    rolling_avg_xgc_5g=excluded.rolling_avg_xgc_5g,
                    games_in_window=excluded.games_in_window,
                    injury_flag=excluded.injury_flag,
                    chance_of_playing=excluded.chance_of_playing,
                    fixture_difficulty=excluded.fixture_difficulty,
                    team_win_prob=excluded.team_win_prob,
                    has_fixture=excluded.has_fixture,
                    snapshot_built_at=excluded.snapshot_built_at
                """,
                (
                    feat["player_id"],
                    self.gameweek_id,
                    feat["fpl_player_id"],
                    feat["team_id"],
                    feat["opponent_team_id"],
                    feat["full_name"],
                    feat["position"],
                    feat["salary"],
                    feat["availability_status"],
                    feat["rolling_avg_fpts_5g"],
                    feat["rolling_avg_fpts_10g"],
                    feat["rolling_avg_xg_5g"],
                    feat["rolling_avg_xa_5g"],
                    feat["rolling_avg_xgc_5g"],
                    feat["games_in_window"],
                    feat["injury_flag"],
                    feat["chance_of_playing"],
                    feat["fixture_difficulty"],
                    feat["team_win_prob"],
                    feat["has_fixture"],
                    built_at,
                ),
            )
        self.connection.commit()


def _availability_adjustment(status: str, chance: int | None) -> tuple[float, str]:
    if chance is not None:
        if chance <= 0:
            return 0.0, "unavailable"
        if chance < 100:
            coeff = max(0.0, min(1.0, chance / 100.0))
            return coeff, f"availability={chance}% coeff={coeff:.2f}"

    if status == "d":
        return 0.85, "doubtful coeff=0.85"

    return 1.0, "available"


def load_feature_snapshots(connection: Connection, gameweek_id: int) -> list[PlayerFeatures]:
    _ensure_projection_schema(connection)
    rows = connection.execute(
        """
        SELECT player_id, fpl_player_id, team_id, opponent_team_id, full_name,
               position, salary, availability_status,
               rolling_avg_fpts_5g, rolling_avg_fpts_10g,
               rolling_avg_xg_5g, rolling_avg_xa_5g, rolling_avg_xgc_5g,
               games_in_window, injury_flag, chance_of_playing,
               fixture_difficulty, team_win_prob, has_fixture
        FROM player_feature_snapshots
        WHERE gameweek_id = ?
        ORDER BY player_id ASC
        """,
        (gameweek_id,),
    ).fetchall()
    return [PlayerFeatures(**dict(row)) for row in rows]


def _ensure_projection_schema(connection: Connection) -> None:
    cols = {
        row[1]
        for row in connection.execute("PRAGMA table_info(player_projections)").fetchall()
    }
    if "backend" not in cols:
        connection.execute(
            "ALTER TABLE player_projections ADD COLUMN backend TEXT NOT NULL DEFAULT 'baseline'"
        )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS player_feature_snapshots (
            id                      INTEGER PRIMARY KEY,
            player_id               INTEGER NOT NULL REFERENCES players(id),
            gameweek_id             INTEGER NOT NULL REFERENCES gameweeks(id),
            fpl_player_id           INTEGER NOT NULL,
            team_id                 INTEGER NOT NULL REFERENCES teams(id),
            opponent_team_id        INTEGER REFERENCES teams(id),
            full_name               TEXT    NOT NULL,
            position                INTEGER NOT NULL,
            salary                  INTEGER NOT NULL,
            availability_status     TEXT,
            rolling_avg_fpts_5g     REAL,
            rolling_avg_fpts_10g    REAL,
            rolling_avg_xg_5g       REAL,
            rolling_avg_xa_5g       REAL,
            rolling_avg_xgc_5g      REAL,
            games_in_window         INTEGER NOT NULL DEFAULT 0,
            injury_flag             INTEGER NOT NULL DEFAULT 0,
            chance_of_playing       INTEGER,
            fixture_difficulty      INTEGER,
            team_win_prob           REAL,
            has_fixture             INTEGER NOT NULL DEFAULT 0,
            snapshot_built_at       TEXT    NOT NULL,
            UNIQUE(player_id, gameweek_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_feature_snapshots_gw ON player_feature_snapshots(gameweek_id)"
    )
    connection.commit()
