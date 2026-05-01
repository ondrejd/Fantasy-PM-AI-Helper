from __future__ import annotations

from dataclasses import dataclass
from sqlite3 import Connection

from fantasy_pl_ai_helper.ai.ollama import OllamaClient
from fantasy_pl_ai_helper.models.projections import ProjectionModel
from fantasy_pl_ai_helper.optimizer.lineup import LineupOptimizer, POSITION_NAMES

_SYSTEM_PROMPT = (
    "Jsi stručný fantasy fotbalový asistent pro Premier League. "
    "Používej pouze poskytnutý kontext. "
    "Nevymýšlej fakta, která nejsou k dispozici. "
    "Vysvětluj výběr hráčů srozumitelně česky a upozorňuj na nejistoty."
)


@dataclass(slots=True)
class LocalAIService:
    connection: Connection
    ollama_client: OllamaClient

    def explain_lineup(self, gameweek_id: int) -> str:
        projections = ProjectionModel(
            connection=self.connection,
            gameweek_id=gameweek_id,
        ).build()

        if not projections:
            return "Žádné projekce pro toto kolo."

        lineup = LineupOptimizer(gameweek_id=gameweek_id).optimize(projections)
        if not lineup:
            return "Nepodařilo se sestavit doporučenou sestavu."

        context = _lineup_context(lineup, projections)
        prompt = (
            f"Dej stručné vysvětlení doporučené sestavy pro kolo {gameweek_id} "
            f"Premier League fantasy ligy.\n\n{context}"
        )
        return self.ollama_client.chat(_SYSTEM_PROMPT, prompt)

    def answer_question(self, gameweek_id: int, question: str) -> str:
        projections = ProjectionModel(
            connection=self.connection,
            gameweek_id=gameweek_id,
        ).build()

        top = sorted(projections, key=lambda p: p["projected_fpts"], reverse=True)[:20]
        context = _projections_context(top, gameweek_id)
        prompt = f"Kontext projekcí pro kolo {gameweek_id}:\n\n{context}\n\nOtázka: {question}"
        return self.ollama_client.chat(_SYSTEM_PROMPT, prompt)


def _lineup_context(lineup: dict, projections: list[dict]) -> str:
    proj_by_id = {p["player_id"]: p for p in projections}
    lines = [
        f"Celkové proj. body: {lineup['total_fpts']:.1f}",
        f"Celková cena: £{lineup['total_salary'] / 10:.1f}M",
        "",
        "Sestava:",
    ]
    for slot in lineup["slots"]:
        p = proj_by_id.get(slot["player_id"])
        notes = p["notes"] if p else ""
        pos_name = POSITION_NAMES.get(slot["position"], "?")
        lines.append(
            f"  {pos_name:4} {slot['full_name']:<25} "
            f"proj={slot['projected_fpts']:.1f} "
            f"£{slot['salary'] / 10:.1f}M  {notes}"
        )
    return "\n".join(lines)


def _projections_context(projections: list[dict], gameweek_id: int) -> str:
    lines = [f"Top projekce pro kolo {gameweek_id}:"]
    for p in projections:
        pos_name = POSITION_NAMES.get(p["position"], "?")
        lines.append(
            f"  {pos_name:4} {p['full_name']:<25} "
            f"proj={p['projected_fpts']:.1f} "
            f"£{p['salary'] / 10:.1f}M"
        )
    return "\n".join(lines)
