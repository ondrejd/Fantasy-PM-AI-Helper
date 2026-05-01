from __future__ import annotations

import json
from dataclasses import dataclass
from sqlite3 import Connection

from fantasy_pl_ai_helper.config import Settings
from fantasy_pl_ai_helper.ingest.fpl_client import FplClient
from fantasy_pl_ai_helper.ingest.odds_client import OddsClient
from fantasy_pl_ai_helper.storage.database import connect
from fantasy_pl_ai_helper.storage.init_db import initialize_database


# FPL position codes → string
POSITION_NAMES = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


@dataclass(slots=True)
class IngestService:
    """Downloads and stores FPL data: teams, players, gameweeks, fixtures, game logs."""

    settings: Settings

    def run(self, step_callback=None) -> dict[str, int]:
        """Run full ingest pipeline. Returns dict of {feed: record_count}."""
        initialize_database(self.settings.database_path)

        client = FplClient(
            base_url=self.settings.fpl_api_base_url,
            timeout=self.settings.http_timeout_seconds,
        )

        counts: dict[str, int] = {}

        with connect(self.settings.database_path) as conn:
            _step(step_callback, "bootstrap")
            bootstrap = client.get_bootstrap()
            counts["teams"] = self._ingest_teams(conn, bootstrap)
            counts["players"] = self._ingest_players(conn, bootstrap)
            counts["gameweeks"] = self._ingest_gameweeks(conn, bootstrap)
            conn.commit()

            _step(step_callback, "fixtures")
            counts["fixtures"] = self._ingest_fixtures(conn, client)
            counts["fixture_odds"] = self._ingest_fixture_odds(conn)
            conn.commit()

            _step(step_callback, "game-logs")
            counts["game_logs"] = self._ingest_game_logs(conn, client, bootstrap)
            conn.commit()

        return counts

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def _ingest_teams(self, conn: Connection, bootstrap: dict) -> int:
        teams = bootstrap.get("teams", [])
        count = 0
        for t in teams:
            conn.execute(
                """
                INSERT INTO teams (
                    fpl_team_id, full_name, short_name,
                    strength_overall_home, strength_overall_away,
                    strength_attack_home, strength_attack_away,
                    strength_defence_home, strength_defence_away
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fpl_team_id) DO UPDATE SET
                    full_name=excluded.full_name,
                    short_name=excluded.short_name,
                    strength_overall_home=excluded.strength_overall_home,
                    strength_overall_away=excluded.strength_overall_away,
                    strength_attack_home=excluded.strength_attack_home,
                    strength_attack_away=excluded.strength_attack_away,
                    strength_defence_home=excluded.strength_defence_home,
                    strength_defence_away=excluded.strength_defence_away,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    int(t["id"]),
                    t.get("name", ""),
                    t.get("short_name", ""),
                    t.get("strength_overall_home"),
                    t.get("strength_overall_away"),
                    t.get("strength_attack_home"),
                    t.get("strength_attack_away"),
                    t.get("strength_defence_home"),
                    t.get("strength_defence_away"),
                ),
            )
            count += 1
        return count

    def _ingest_players(self, conn: Connection, bootstrap: dict) -> int:
        elements = bootstrap.get("elements", [])
        count = 0
        for p in elements:
            fpl_team_id = int(p.get("team", 0))
            team_row = conn.execute(
                "SELECT id FROM teams WHERE fpl_team_id = ?", (fpl_team_id,)
            ).fetchone()
            team_db_id = int(team_row[0]) if team_row else None

            status = p.get("status", "a")
            is_active = 0 if status in ("u", "n") else 1
            chance = p.get("chance_of_playing_next_round")

            conn.execute(
                """
                INSERT INTO players (
                    fpl_player_id, full_name, first_name, last_name,
                    position, team_id, now_cost, status,
                    chance_of_playing_next_round, is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fpl_player_id) DO UPDATE SET
                    full_name=excluded.full_name,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name,
                    position=excluded.position,
                    team_id=excluded.team_id,
                    now_cost=excluded.now_cost,
                    status=excluded.status,
                    chance_of_playing_next_round=excluded.chance_of_playing_next_round,
                    is_active=excluded.is_active,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    int(p["id"]),
                    p.get("web_name", ""),
                    p.get("first_name", ""),
                    p.get("second_name", ""),
                    int(p.get("element_type", 4)),
                    team_db_id,
                    int(p.get("now_cost", 0)),
                    status,
                    chance,
                    is_active,
                ),
            )

            # Upsert injury record for unavailable/doubtful players
            news = p.get("news", "")
            if status in ("d", "i", "s") or news:
                conn.execute(
                    """
                    INSERT INTO injuries (player_id, injury_status, news, chance_of_playing_next_round, is_active)
                    VALUES (
                        (SELECT id FROM players WHERE fpl_player_id = ?),
                        ?, ?, ?, 1
                    )
                    ON CONFLICT(player_id) DO UPDATE SET
                        injury_status=excluded.injury_status,
                        news=excluded.news,
                        chance_of_playing_next_round=excluded.chance_of_playing_next_round,
                        is_active=1,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (int(p["id"]), status, news, chance),
                )
            else:
                # Mark previous injuries as inactive
                conn.execute(
                    """
                    UPDATE injuries SET is_active=0, updated_at=CURRENT_TIMESTAMP
                    WHERE player_id = (SELECT id FROM players WHERE fpl_player_id = ?)
                      AND is_active = 1
                    """,
                    (int(p["id"]),),
                )

            count += 1
        return count

    def _ingest_gameweeks(self, conn: Connection, bootstrap: dict) -> int:
        events = bootstrap.get("events", [])
        count = 0

        # Ensure a season row exists
        season_label = _infer_season_label(events)
        conn.execute(
            """
            INSERT INTO seasons (fpl_season_id, season_label, is_current)
            VALUES (?, ?, 1)
            ON CONFLICT(fpl_season_id) DO UPDATE SET
                season_label=excluded.season_label,
                is_current=1
            """,
            (season_label, season_label),
        )
        season_row = conn.execute(
            "SELECT id FROM seasons WHERE fpl_season_id = ?", (season_label,)
        ).fetchone()
        season_db_id = int(season_row[0])

        for ev in events:
            conn.execute(
                """
                INSERT INTO gameweeks (fpl_event_id, season_id, name, deadline_time,
                    average_entry_score, is_current, is_next, finished)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fpl_event_id) DO UPDATE SET
                    name=excluded.name,
                    deadline_time=excluded.deadline_time,
                    average_entry_score=excluded.average_entry_score,
                    is_current=excluded.is_current,
                    is_next=excluded.is_next,
                    finished=excluded.finished,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    int(ev["id"]),
                    season_db_id,
                    ev.get("name", f"Gameweek {ev['id']}"),
                    ev.get("deadline_time"),
                    ev.get("average_entry_score"),
                    1 if ev.get("is_current") else 0,
                    1 if ev.get("is_next") else 0,
                    1 if ev.get("finished") else 0,
                ),
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------

    def _ingest_fixtures(self, conn: Connection, client: FplClient) -> int:
        season_row = conn.execute("SELECT id FROM seasons ORDER BY id DESC LIMIT 1").fetchone()
        if not season_row:
            return 0
        season_db_id = int(season_row[0])

        fixtures = client.get_fixtures()
        count = 0
        for f in fixtures:
            fpl_event_id = f.get("event")
            gw_row = None
            if fpl_event_id:
                gw_row = conn.execute(
                    "SELECT id FROM gameweeks WHERE fpl_event_id = ?", (int(fpl_event_id),)
                ).fetchone()

            home_row = conn.execute(
                "SELECT id FROM teams WHERE fpl_team_id = ?", (int(f["team_h"]),)
            ).fetchone()
            away_row = conn.execute(
                "SELECT id FROM teams WHERE fpl_team_id = ?", (int(f["team_a"]),)
            ).fetchone()
            if not home_row or not away_row:
                continue

            conn.execute(
                """
                INSERT INTO fixtures (
                    fpl_fixture_id, gameweek_id, season_id, kickoff_time,
                    home_team_id, away_team_id, started, finished, finished_provisional,
                    home_score, away_score, home_difficulty, away_difficulty
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fpl_fixture_id) DO UPDATE SET
                    gameweek_id=excluded.gameweek_id,
                    kickoff_time=excluded.kickoff_time,
                    started=excluded.started,
                    finished=excluded.finished,
                    finished_provisional=excluded.finished_provisional,
                    home_score=excluded.home_score,
                    away_score=excluded.away_score,
                    home_difficulty=excluded.home_difficulty,
                    away_difficulty=excluded.away_difficulty,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    int(f["id"]),
                    int(gw_row[0]) if gw_row else None,
                    season_db_id,
                    f.get("kickoff_time"),
                    int(home_row[0]),
                    int(away_row[0]),
                    1 if f.get("started") else 0,
                    1 if f.get("finished") else 0,
                    1 if f.get("finished_provisional") else 0,
                    f.get("team_h_score"),
                    f.get("team_a_score"),
                    f.get("team_h_difficulty"),
                    f.get("team_a_difficulty"),
                ),
            )
            count += 1
        return count

    def _ingest_fixture_odds(self, conn: Connection) -> int:
        if not self.settings.odds_api_key:
            return 0

        client = OddsClient(
            base_url=self.settings.odds_api_base_url,
            api_key=self.settings.odds_api_key,
            timeout=self.settings.http_timeout_seconds,
        )
        events = client.get_premier_league_h2h()

        team_rows = conn.execute("SELECT id, full_name, short_name FROM teams").fetchall()
        team_name_map: dict[str, int] = {}
        for row in team_rows:
            team_name_map[_normalize_team_name(row["full_name"])] = int(row["id"])
            team_name_map[_normalize_team_name(row["short_name"])] = int(row["id"])

        count = 0
        for event in events:
            home_team_id = team_name_map.get(_normalize_team_name(event.get("home_team", "")))
            away_team_id = team_name_map.get(_normalize_team_name(event.get("away_team", "")))
            if not home_team_id or not away_team_id:
                continue

            fixture_row = conn.execute(
                """
                SELECT id FROM fixtures
                WHERE home_team_id = ?
                  AND away_team_id = ?
                  AND finished = 0
                ORDER BY kickoff_time ASC
                LIMIT 1
                """,
                (home_team_id, away_team_id),
            ).fetchone()
            if not fixture_row:
                continue

            probs = _market_probabilities(event)
            if probs is None:
                continue

            conn.execute(
                """
                INSERT INTO fixture_odds (
                    fixture_id, provider, bookmaker,
                    home_win_prob, draw_prob, away_win_prob,
                    home_decimal_odds, draw_decimal_odds, away_decimal_odds,
                    fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(fixture_id, provider) DO UPDATE SET
                    bookmaker=excluded.bookmaker,
                    home_win_prob=excluded.home_win_prob,
                    draw_prob=excluded.draw_prob,
                    away_win_prob=excluded.away_win_prob,
                    home_decimal_odds=excluded.home_decimal_odds,
                    draw_decimal_odds=excluded.draw_decimal_odds,
                    away_decimal_odds=excluded.away_decimal_odds,
                    fetched_at=CURRENT_TIMESTAMP
                """,
                (
                    int(fixture_row[0]),
                    "the-odds-api",
                    probs["bookmaker"],
                    probs["home_win_prob"],
                    probs["draw_prob"],
                    probs["away_win_prob"],
                    probs["home_decimal_odds"],
                    probs["draw_decimal_odds"],
                    probs["away_decimal_odds"],
                ),
            )
            count += 1

        return count

    # ------------------------------------------------------------------
    # Game logs
    # ------------------------------------------------------------------

    def _ingest_game_logs(
        self, conn: Connection, client: FplClient, bootstrap: dict
    ) -> int:
        elements = bootstrap.get("elements", [])
        total = 0

        # Only fetch history for active players
        for p in elements:
            player_row = conn.execute(
                "SELECT id FROM players WHERE fpl_player_id = ?", (int(p["id"]),)
            ).fetchone()
            if not player_row:
                continue
            player_db_id = int(player_row[0])

            try:
                summary = client.get_element_summary(int(p["id"]))
            except Exception:
                continue

            history = summary.get("history", [])
            for h in history:
                fpl_fixture_id = h.get("fixture")
                if not fpl_fixture_id:
                    continue
                fixture_row = conn.execute(
                    "SELECT id, home_team_id, away_team_id, home_score, away_score FROM fixtures WHERE fpl_fixture_id = ?",
                    (int(fpl_fixture_id),),
                ).fetchone()
                if not fixture_row:
                    continue

                fixture_db_id = int(fixture_row["id"])
                was_home = 1 if h.get("was_home") else 0
                home_score = fixture_row["home_score"]
                away_score = fixture_row["away_score"]

                result_type = _calc_result(was_home, home_score, away_score)

                team_id = int(fixture_row["home_team_id"] if was_home else fixture_row["away_team_id"])
                opp_id = int(fixture_row["away_team_id"] if was_home else fixture_row["home_team_id"])

                conn.execute(
                    """
                    INSERT INTO player_game_logs (
                        player_id, fixture_id, team_id, opponent_team_id, was_home,
                        minutes, goals_scored, assists, clean_sheets, goals_conceded,
                        own_goals, penalties_saved, penalties_missed, yellow_cards, red_cards,
                        saves, bonus, bps,
                        expected_goals, expected_assists, expected_goals_conceded,
                        influence, creativity, threat,
                        result_type, fpl_total_points, raw_payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(player_id, fixture_id) DO UPDATE SET
                        minutes=excluded.minutes,
                        goals_scored=excluded.goals_scored,
                        assists=excluded.assists,
                        clean_sheets=excluded.clean_sheets,
                        goals_conceded=excluded.goals_conceded,
                        own_goals=excluded.own_goals,
                        penalties_saved=excluded.penalties_saved,
                        penalties_missed=excluded.penalties_missed,
                        yellow_cards=excluded.yellow_cards,
                        red_cards=excluded.red_cards,
                        saves=excluded.saves,
                        bonus=excluded.bonus,
                        bps=excluded.bps,
                        expected_goals=excluded.expected_goals,
                        expected_assists=excluded.expected_assists,
                        expected_goals_conceded=excluded.expected_goals_conceded,
                        influence=excluded.influence,
                        creativity=excluded.creativity,
                        threat=excluded.threat,
                        result_type=excluded.result_type,
                        fpl_total_points=excluded.fpl_total_points,
                        raw_payload=excluded.raw_payload
                    """,
                    (
                        player_db_id,
                        fixture_db_id,
                        team_id,
                        opp_id,
                        was_home,
                        int(h.get("minutes", 0)),
                        int(h.get("goals_scored", 0)),
                        int(h.get("assists", 0)),
                        int(h.get("clean_sheets", 0)),
                        int(h.get("goals_conceded", 0)),
                        int(h.get("own_goals", 0)),
                        int(h.get("penalties_saved", 0)),
                        int(h.get("penalties_missed", 0)),
                        int(h.get("yellow_cards", 0)),
                        int(h.get("red_cards", 0)),
                        int(h.get("saves", 0)),
                        int(h.get("bonus", 0)),
                        int(h.get("bps", 0)),
                        _float_or_none(h.get("expected_goals")),
                        _float_or_none(h.get("expected_assists")),
                        _float_or_none(h.get("expected_goals_conceded")),
                        _float_or_none(h.get("influence")),
                        _float_or_none(h.get("creativity")),
                        _float_or_none(h.get("threat")),
                        result_type,
                        int(h.get("total_points", 0)),
                        json.dumps(h),
                    ),
                )
                total += 1

        return total


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _calc_result(was_home: int, home_score, away_score) -> str | None:
    if home_score is None or away_score is None:
        return None
    h, a = int(home_score), int(away_score)
    if h == a:
        return "D"
    if was_home:
        return "W" if h > a else "L"
    return "W" if a > h else "L"


def _float_or_none(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _infer_season_label(events: list[dict]) -> str:
    """Guess season label from event names. Falls back to 'unknown'."""
    for ev in events:
        # FPL event names are like "Gameweek 1"
        pass
    # Use a fixed label for now; the FPL API doesn't expose season directly
    import datetime
    year = datetime.date.today().year
    month = datetime.date.today().month
    # Season starts in August
    if month >= 8:
        return f"{year}{year + 1}"
    return f"{year - 1}{year}"


def _step(callback, name: str) -> None:
    if callback:
        callback(name)


def _normalize_team_name(name: str) -> str:
    aliases = {
        "man utd": "manchesterunited",
        "man united": "manchesterunited",
        "man city": "manchestercity",
        "spurs": "tottenhamhotspur",
        "wolves": "wolverhamptonwanderers",
        "brighton": "brightonandhovealbion",
        "newcastle": "newcastleunited",
        "forest": "nottinghamforest",
    }
    lowered = name.lower().strip()
    if lowered in aliases:
        return aliases[lowered]
    return "".join(ch for ch in lowered if ch.isalnum())


def _market_probabilities(event: dict) -> dict[str, float | str] | None:
    bookmakers = event.get("bookmakers") or []
    if not bookmakers:
        return None

    home_name = event.get("home_team")
    away_name = event.get("away_team")
    home_probs: list[float] = []
    draw_probs: list[float] = []
    away_probs: list[float] = []
    home_odds: list[float] = []
    draw_odds: list[float] = []
    away_odds: list[float] = []

    for bookmaker in bookmakers:
        markets = bookmaker.get("markets") or []
        h2h = next((market for market in markets if market.get("key") == "h2h"), None)
        if not h2h:
            continue

        outcomes = h2h.get("outcomes") or []
        price_by_name = {outcome.get("name"): outcome.get("price") for outcome in outcomes}
        home_price = price_by_name.get(home_name)
        draw_price = price_by_name.get("Draw")
        away_price = price_by_name.get(away_name)
        if not home_price or not draw_price or not away_price:
            continue

        inv_home = 1.0 / float(home_price)
        inv_draw = 1.0 / float(draw_price)
        inv_away = 1.0 / float(away_price)
        total = inv_home + inv_draw + inv_away
        if total <= 0.0:
            continue

        home_probs.append(inv_home / total)
        draw_probs.append(inv_draw / total)
        away_probs.append(inv_away / total)
        home_odds.append(float(home_price))
        draw_odds.append(float(draw_price))
        away_odds.append(float(away_price))

    if not home_probs:
        return None

    return {
        "bookmaker": str(bookmakers[0].get("title") or "mixed"),
        "home_win_prob": sum(home_probs) / len(home_probs),
        "draw_prob": sum(draw_probs) / len(draw_probs),
        "away_win_prob": sum(away_probs) / len(away_probs),
        "home_decimal_odds": sum(home_odds) / len(home_odds),
        "draw_decimal_odds": sum(draw_odds) / len(draw_odds),
        "away_decimal_odds": sum(away_odds) / len(away_odds),
    }
