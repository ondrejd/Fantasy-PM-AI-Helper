from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from fantasy_pl_ai_helper.models.projections import PlayerProjection

# Position codes
GK = 1
DEF = 2
MID = 3
FWD = 4

POSITION_NAMES = {GK: "GK", DEF: "DEF", MID: "MID", FWD: "FWD"}


class LineupSlot(TypedDict):
    slot: str         # e.g. "GK", "DEF1", "MID2", "FWD1"
    player_id: int
    fpl_player_id: int
    full_name: str
    position: int
    salary: int
    projected_fpts: float
    slot_fpts: float
    team_id: int | None
    team_name: str | None
    team_short_name: str | None
    team_fpl_id: int | None
    team_logo_url: str | None


class OptimizedLineup(TypedDict):
    gameweek_id: int
    total_fpts: float
    total_salary: int   # £0.1M units
    slots: list[LineupSlot]


@dataclass(slots=True)
class LineupOptimizer:
    """Optimizes a fantasy football lineup for Premier League.

    Constraints:
    - 1 GK (goalkeeper)
    - 1-5 DEF (defenders)
    - 1-5 MID (midfielders)
    - 1-4 FWD (forwards)
    - DEF + MID + FWD = 10 (outfield players)
    - Total = 11 players
    - Total salary ≤ salary_cap (default 1000 = £100M)

    Uses a greedy approach: tries all valid formations, picks the one with
    highest total projected_fpts while respecting the salary constraint.
    """

    gameweek_id: int
    salary_cap: int = 1000  # £100M in 0.1M units
    excluded_player_ids: set[int] = field(default_factory=set)
    locked_player_ids: set[int] = field(default_factory=set)

    # Valid formations: (n_def, n_mid, n_fwd) where sum = 10
    VALID_FORMATIONS: tuple[tuple[int, int, int], ...] = (
        (4, 4, 2),
        (4, 3, 3),
        (3, 5, 2),
        (3, 4, 3),
        (5, 4, 1),
        (5, 3, 2),
        (4, 5, 1),
        (3, 3, 4),
        (4, 2, 4),
        (5, 2, 3),
    )

    def optimize(self, projections: list[PlayerProjection]) -> OptimizedLineup | None:
        """Return the best valid lineup or None if constraints cannot be met."""
        # Filter out excluded and ineligible players
        available = [
            p for p in projections
            if p["player_id"] not in self.excluded_player_ids
            and p["projected_fpts"] > 0
        ]

        locked = [p for p in available if p["player_id"] in self.locked_player_ids]

        # Split by position
        gks = _sorted_by_fpts([p for p in available if p["position"] == GK])
        defs = _sorted_by_fpts([p for p in available if p["position"] == DEF])
        mids = _sorted_by_fpts([p for p in available if p["position"] == MID])
        fwds = _sorted_by_fpts([p for p in available if p["position"] == FWD])

        if not gks:
            return None

        best_lineup: OptimizedLineup | None = None
        best_total = -1.0

        gk = gks[0]  # always pick best GK (within salary constraint)

        for n_def, n_mid, n_fwd in self.VALID_FORMATIONS:
            if len(defs) < n_def or len(mids) < n_mid or len(fwds) < n_fwd:
                continue

            # Greedy pick for each position
            sel_def = _pick_top(defs, n_def)
            sel_mid = _pick_top(mids, n_mid)
            sel_fwd = _pick_top(fwds, n_fwd)

            all_players = [gk] + sel_def + sel_mid + sel_fwd
            total_salary = sum(p["salary"] for p in all_players)

            if total_salary > self.salary_cap:
                # Try to fit within budget: swap most expensive players for cheaper
                all_players = self._fit_budget(
                    gk, sel_def, sel_mid, sel_fwd,
                    defs, mids, fwds,
                    n_def, n_mid, n_fwd,
                )
                if all_players is None:
                    continue
                total_salary = sum(p["salary"] for p in all_players)

            total_fpts = sum(p["projected_fpts"] for p in all_players)

            if total_fpts > best_total:
                best_total = total_fpts
                best_lineup = _build_lineup(self.gameweek_id, all_players, total_salary)

        return best_lineup

    def _fit_budget(
        self,
        gk: PlayerProjection,
        sel_def: list[PlayerProjection],
        sel_mid: list[PlayerProjection],
        sel_fwd: list[PlayerProjection],
        all_defs: list[PlayerProjection],
        all_mids: list[PlayerProjection],
        all_fwds: list[PlayerProjection],
        n_def: int,
        n_mid: int,
        n_fwd: int,
    ) -> list[PlayerProjection] | None:
        """Try to find a valid lineup within salary_cap for this formation.

        Uses a simple greedy: iterate salary-sorted candidates and pick
        the cheapest combination that still maximises points.
        """
        budget_left = self.salary_cap - gk["salary"]
        if budget_left < 0:
            return None

        # Sort each position pool by best fpts/salary ratio
        def ratio(p: PlayerProjection) -> float:
            return p["projected_fpts"] / max(p["salary"], 1)

        d_pool = sorted(all_defs, key=ratio, reverse=True)
        m_pool = sorted(all_mids, key=ratio, reverse=True)
        f_pool = sorted(all_fwds, key=ratio, reverse=True)

        if len(d_pool) < n_def or len(m_pool) < n_mid or len(f_pool) < n_fwd:
            return None

        # Brute-force only within small windows for speed
        best: list[PlayerProjection] | None = None
        best_score = -1.0

        d_candidates = d_pool[: min(len(d_pool), n_def + 3)]
        m_candidates = m_pool[: min(len(m_pool), n_mid + 3)]
        f_candidates = f_pool[: min(len(f_pool), n_fwd + 3)]

        from itertools import combinations

        for d_sel in combinations(d_candidates, n_def):
            for m_sel in combinations(m_candidates, n_mid):
                for f_sel in combinations(f_candidates, n_fwd):
                    players = list(d_sel) + list(m_sel) + list(f_sel)
                    total_sal = sum(p["salary"] for p in players)
                    if total_sal <= budget_left:
                        total_fpts = sum(p["projected_fpts"] for p in players)
                        if total_fpts > best_score:
                            best_score = total_fpts
                            best = players

        if best is None:
            return None
        return [gk] + best


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sorted_by_fpts(players: list[PlayerProjection]) -> list[PlayerProjection]:
    return sorted(players, key=lambda p: p["projected_fpts"], reverse=True)


def _pick_top(players: list[PlayerProjection], n: int) -> list[PlayerProjection]:
    return players[:n]


def _build_lineup(
    gameweek_id: int,
    players: list[PlayerProjection],
    total_salary: int,
) -> OptimizedLineup:
    slots: list[LineupSlot] = []
    pos_counts: dict[int, int] = {}
    for p in players:
        pos = p["position"]
        pos_counts[pos] = pos_counts.get(pos, 0) + 1
        slot_name = f"{POSITION_NAMES[pos]}{pos_counts[pos]}" if pos_counts[pos] > 1 else POSITION_NAMES[pos]
        slots.append(
            LineupSlot(
                slot=slot_name,
                player_id=p["player_id"],
                fpl_player_id=p["fpl_player_id"],
                full_name=p["full_name"],
                position=pos,
                salary=p["salary"],
                projected_fpts=p["projected_fpts"],
                slot_fpts=p["projected_fpts"],
                team_id=p.get("team_id"),
                team_name=p.get("team_name"),
                team_short_name=p.get("team_short_name"),
                team_fpl_id=p.get("team_fpl_id"),
                team_logo_url=p.get("team_logo_url"),
            )
        )

    return OptimizedLineup(
        gameweek_id=gameweek_id,
        total_fpts=round(sum(p["projected_fpts"] for p in players), 4),
        total_salary=total_salary,
        slots=slots,
    )
