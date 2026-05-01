from __future__ import annotations

"""Fantasy Premier League custom scoring engine.

Bodování se liší dle pozice:
  GK  = position 1
  DEF = position 2
  MID = position 3
  FWD = position 4

Zdroj scoring pravidel: fantasy-bodovani-fotbal.md

Poznámka: Některé statistiky (střely, souboje, kličky, kluzy, centry,
klíčové přihrávky, rohy, ofsajdy, fauly) nejsou dostupné z FPL API
a jsou proto v tomto baseline modelu vynechány (= 0 bodů).
Pro plné bodování by bylo třeba doplnit data z dalšího zdroje (např. understat,
SofaScore nebo StatsBomb).
"""

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Scoring tables — indexed by position (1=GK, 2=DEF, 3=MID, 4=FWD)
# ---------------------------------------------------------------------------

# Body za gól
GOAL_POINTS: dict[int, int] = {1: 30, 2: 24, 3: 18, 4: 12}

# Body za vítězný gól (scored the match-winning goal — hard to determine from
# FPL API alone; we approximate as 0 in baseline)
WINNING_GOAL_POINTS: dict[int, int] = {1: 10, 2: 6, 3: 3, 4: 2}

# Body za hattrick (additional bonus, on top of goal points)
HATTRICK_BONUS: dict[int, int] = {1: 50, 2: 24, 3: 18, 4: 12}

# Body za asistenci
ASSIST_POINTS: dict[int, int] = {1: 15, 2: 12, 3: 8, 4: 6}

# Body za vlastní gól (negative)
OWN_GOAL_POINTS: dict[int, int] = {1: -8, 2: -8, 3: -10, 4: -12}

# Body za neproměněnou penaltu
PENALTY_MISS_POINTS: dict[int, int] = {1: -6, 2: -6, 3: -6, 4: -6}

# Body za žlutou kartu
YELLOW_CARD_POINTS: dict[int, int] = {1: -4, 2: -3, 3: -3, 4: -4}

# Body za červenou kartu
RED_CARD_POINTS: dict[int, int] = {1: -10, 2: -8, 3: -8, 4: -10}

# Body za výhru / prohru / remízu
WIN_POINTS: dict[int, int] = {1: 2, 2: 2, 3: 2, 4: 2}
LOSS_POINTS: dict[int, int] = {1: -2, 2: -2, 3: -2, 4: -2}
DRAW_POINTS: dict[int, int] = {1: 1, 2: 1, 3: 1, 4: 1}

# Body za čisté konto
CLEAN_SHEET_POINTS: dict[int, int] = {1: 3, 2: 2, 3: 1, 4: 1}

# Body za odehraných 20 minut (za každých 20 minut = 1 bod)
PER_20_MIN_POINTS: int = 1

# GK specifics
GK_SAVE_POINTS: int = 3           # za každou chycenou střelu
GK_PENALTY_SAVED_POINTS: int = 8  # za každou chycenou penaltu
GK_GOAL_CONCEDED_POINTS: int = -3 # za každý obdržený gól


@dataclass(slots=True)
class ScoringEngine:
    """Computes fantasy points from a player_game_logs row (dict)."""

    def score_game_log(self, row: dict, position: int | None = None) -> float:
        """Score a single game-log dict.

        Args:
            row: dict with keys matching player_game_logs columns.
            position: FPL position (1-4). If None, tries row['position'].
        """
        if position is None:
            position = int(row.get("position", 4))

        points: float = 0.0

        # --- Minutes played ---
        minutes = int(row.get("minutes", 0))
        if minutes >= 20:
            points += PER_20_MIN_POINTS * (minutes // 20)

        # --- Goals ---
        goals = int(row.get("goals_scored", 0))
        if goals > 0:
            points += goals * GOAL_POINTS[position]
        if goals >= 3:
            points += HATTRICK_BONUS[position]

        # --- Assists ---
        assists = int(row.get("assists", 0))
        points += assists * ASSIST_POINTS[position]

        # --- Own goals ---
        own_goals = int(row.get("own_goals", 0))
        points += own_goals * OWN_GOAL_POINTS[position]

        # --- Clean sheet ---
        clean_sheet = int(row.get("clean_sheets", 0))
        if clean_sheet:
            points += CLEAN_SHEET_POINTS[position]

        # --- Result: W / D / L ---
        result = row.get("result_type")
        if result == "W":
            points += WIN_POINTS[position]
        elif result == "L":
            points += LOSS_POINTS[position]
        elif result == "D":
            points += DRAW_POINTS[position]

        # --- Cards ---
        yellow = int(row.get("yellow_cards", 0))
        red = int(row.get("red_cards", 0))
        points += yellow * YELLOW_CARD_POINTS[position]
        points += red * RED_CARD_POINTS[position]

        # --- Missed penalty ---
        pen_miss = int(row.get("penalties_missed", 0))
        points += pen_miss * PENALTY_MISS_POINTS[position]

        # --- GK-specific ---
        if position == 1:
            saves = int(row.get("saves", 0))
            points += saves * GK_SAVE_POINTS

            pen_saved = int(row.get("penalties_saved", 0))
            points += pen_saved * GK_PENALTY_SAVED_POINTS

            goals_conceded = int(row.get("goals_conceded", 0))
            points += goals_conceded * GK_GOAL_CONCEDED_POINTS

        return round(points, 4)

    def score_expected(self, row: dict, position: int | None = None) -> float:
        """Score using xStats from FPL (expected goals, assists, etc.)
        as an alternative to actual stats for projection purposes.
        """
        if position is None:
            position = int(row.get("position", 4))

        points: float = 0.0

        # Use expected goals as proxy
        xg = float(row.get("expected_goals") or 0.0)
        xa = float(row.get("expected_assists") or 0.0)
        xgc = float(row.get("expected_goals_conceded") or 0.0)
        minutes = int(row.get("minutes", 0))

        if minutes >= 20:
            points += PER_20_MIN_POINTS * (minutes // 20)

        points += xg * GOAL_POINTS[position]
        points += xa * ASSIST_POINTS[position]

        # xG clean sheet proxy: low xGC → partial clean sheet credit
        if position in (1, 2):
            # Approx clean sheet probability from xGC
            cs_prob = max(0.0, 1.0 - xgc)
            points += cs_prob * CLEAN_SHEET_POINTS[position]

        if position == 1:
            # GK saves approximation from xGC (shots → approx saves)
            avg_saves = xgc * 3  # rough: ~3 saves per expected goal conceded
            points += avg_saves * GK_SAVE_POINTS
            # Penalise for expected goals conceded
            points += xgc * GK_GOAL_CONCEDED_POINTS

        return round(points, 4)
