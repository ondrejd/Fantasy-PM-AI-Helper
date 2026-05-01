from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from fantasy_pl_ai_helper.ai import LocalAIService, OllamaClient, OllamaError
from fantasy_pl_ai_helper.config import get_settings
from fantasy_pl_ai_helper.ingest.service import IngestService
from fantasy_pl_ai_helper.models.evaluation import ProjectionEvaluator
from fantasy_pl_ai_helper.models.ml import MLProjectionTrainer
from fantasy_pl_ai_helper.models.projections import ProjectionModel
from fantasy_pl_ai_helper.optimizer.lineup import LineupOptimizer, POSITION_NAMES
from fantasy_pl_ai_helper.storage.database import connect


def _fmt_num(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "–"
    return f"{value:.{digits}f}"


def _gw_label(salary: int) -> str:
    return f"£{salary / 10:.1f}M"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fantasy-pl",
        description="Backend utility commands for Fantasy Premier League AI Helper.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("update-data", help="Fetch and store current FPL data.")

    rebuild_p = subparsers.add_parser(
        "rebuild-projections",
        help="Recompute lineup projections from stored data.",
    )
    rebuild_p.add_argument("--gameweek", type=int, default=None,
        help="Gameweek number (default: current).")
    rebuild_p.add_argument("--backend", choices=["baseline", "ml"], default=None,
        help="Projection backend to use.")
    rebuild_p.add_argument("--ml-model-path", default=None,
        help="Path to trained ML model artifact.")

    train_ml_p = subparsers.add_parser(
        "train-ml-model",
        help="Train ML projection model from historical gameweeks.",
    )
    train_ml_p.add_argument("--upto-gameweek", type=int, default=None,
        help="Use finished gameweeks strictly before this DB gameweek id.")
    train_ml_p.add_argument("--output", default=None,
        help="Output path for trained model artifact.")

    recommend_p = subparsers.add_parser(
        "recommend-lineup",
        help="Build a recommended lineup for the given gameweek.",
    )
    recommend_p.add_argument("--gameweek", type=int, default=None,
        help="Gameweek number (default: next).")
    recommend_p.add_argument("--exclude", nargs="*", type=int, default=[],
        help="Player DB IDs to exclude.")
    recommend_p.add_argument("--lock", nargs="*", type=int, default=[],
        help="Player DB IDs to force-include.")
    recommend_p.add_argument("--backend", choices=["baseline", "ml"], default=None,
        help="Projection backend to use.")
    recommend_p.add_argument("--ml-model-path", default=None,
        help="Path to trained ML model artifact.")

    proj_p = subparsers.add_parser(
        "show-projections",
        help="Show top projected players for a gameweek.",
    )
    proj_p.add_argument("--gameweek", type=int, default=None)
    proj_p.add_argument("--top", type=int, default=20)
    proj_p.add_argument("--position", type=int, default=None,
        help="Filter by position (1=GK, 2=DEF, 3=MID, 4=FWD).")

    eval_p = subparsers.add_parser("evaluate",
        help="Evaluate stored projections against realized points.")
    eval_p.add_argument("--gameweek", type=int, default=None)
    eval_p.add_argument("--ml-model-path", default=None,
        help="Path to trained ML model artifact used for backend comparison.")

    report_p = subparsers.add_parser("evaluate-report",
        help="Show historical evaluation trend.")
    report_p.add_argument("--rows", type=int, default=10)

    explain_p = subparsers.add_parser("explain-lineup-ai",
        help="Use local LLM to explain the recommended lineup.")
    explain_p.add_argument("--gameweek", type=int, default=None)
    explain_p.add_argument("--model", default=None)

    ask_p = subparsers.add_parser("ask-ai",
        help="Ask local LLM a question about the upcoming gameweek.")
    ask_p.add_argument("question", help="Question to ask.")
    ask_p.add_argument("--gameweek", type=int, default=None)
    ask_p.add_argument("--model", default=None)

    return parser


def _resolve_gameweek(connection, gw_arg: int | None, prefer_next: bool = False) -> int | None:
    if gw_arg is not None:
        row = connection.execute(
            "SELECT id FROM gameweeks WHERE fpl_event_id = ?", (gw_arg,)
        ).fetchone()
        return int(row[0]) if row else None

    col = "is_next" if prefer_next else "is_current"
    row = connection.execute(
        f"SELECT id FROM gameweeks WHERE {col} = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row:
        return int(row[0])
    # Fallback: next unfinished
    row = connection.execute(
        "SELECT id FROM gameweeks WHERE finished = 0 ORDER BY id ASC LIMIT 1"
    ).fetchone()
    return int(row[0]) if row else None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "update-data":
        settings = get_settings()
        IngestService(settings=settings).run()
        print(f"Data updated. DB: {settings.database_path}")
        return 0

    if args.command == "train-ml-model":
        settings = get_settings()
        output_path = Path(args.output).expanduser().resolve() if args.output else settings.model_artifact_path
        with connect(settings.database_path) as conn:
            trainer = MLProjectionTrainer(connection=conn)
            try:
                summary = trainer.train(output_path=output_path, upto_gameweek_id=args.upto_gameweek)
            except ValueError as exc:
                print(f"ML training error: {exc}")
                return 1

        print(
            f"ML model trained: {summary['model_path']}  "
            f"samples={summary['sample_count']} gameweeks={summary['gameweek_count']}  "
            f"features={summary['feature_count']} target_mean={summary['target_mean']:.2f}"
        )
        return 0

    if args.command == "rebuild-projections":
        settings = get_settings()
        backend = args.backend or settings.projection_backend
        model_path = Path(args.ml_model_path).expanduser().resolve() if args.ml_model_path else settings.model_artifact_path
        with connect(settings.database_path) as conn:
            gw_id = _resolve_gameweek(conn, getattr(args, "gameweek", None), prefer_next=True)
        if not gw_id:
            print("No upcoming gameweek found. Run update-data first.")
            return 1
        with connect(settings.database_path) as conn:
            model = ProjectionModel(connection=conn, gameweek_id=gw_id, backend=backend, model_artifact_path=model_path)
            try:
                projections = model.build()
            except FileNotFoundError as exc:
                print(f"Projection error: {exc}")
                return 1
        if not projections:
            print(f"No fixtures found for gameweek_id={gw_id}.")
            return 0
        top = sorted(projections, key=lambda p: p["projected_fpts"], reverse=True)[:10]
        print(f"Built {len(projections)} projection(s) for gameweek_id={gw_id} using backend={backend}.")
        print(f"\n{'Rank':<5} {'Player':<26} {'Pos':<4} {'Proj':>6}  {'5g':>6}  {'10g':>6}  {'Salary':>7}  Notes")
        print("-" * 88)
        for i, p in enumerate(top, 1):
            pos = POSITION_NAMES.get(p["position"], "?")
            avg5 = _fmt_num(p["rolling_avg_fpts_5g"])
            avg10 = _fmt_num(p["rolling_avg_fpts_10g"])
            flag = " INJ" if p["injury_flag"] else ""
            print(
                f"{i:<5} {p['full_name']:<26} {pos:<4} "
                f"{p['projected_fpts']:>6.1f}  {avg5:>6}  {avg10:>6}  "
                f"{_gw_label(p['salary']):>7}  {p['notes']}{flag}"
            )
        return 0

    if args.command == "show-projections":
        settings = get_settings()
        with connect(settings.database_path) as conn:
            gw_id = _resolve_gameweek(conn, getattr(args, "gameweek", None), prefer_next=True)
            if not gw_id:
                print("No gameweek found.")
                return 1
            pos_filter = getattr(args, "position", None)
            top_n = getattr(args, "top", 20)
            query = """
                SELECT pp.*, p.full_name AS player_name
                FROM player_projections pp
                JOIN players p ON p.id = pp.player_id
                WHERE pp.gameweek_id = ?
            """
            params: list = [gw_id]
            if pos_filter:
                query += " AND pp.position = ?"
                params.append(pos_filter)
            query += " ORDER BY pp.projected_fpts DESC LIMIT ?"
            params.append(top_n)
            rows = conn.execute(query, params).fetchall()

        if not rows:
            print(f"No projections for gameweek_id={gw_id}. Run rebuild-projections first.")
            return 0

        print(f"\n{'Rank':<5} {'Player':<26} {'Pos':<4} {'Proj':>6}  {'5g':>6}  {'10g':>6}  {'Salary':>7}  Notes")
        print("-" * 88)
        for i, row in enumerate(rows, 1):
            pos = POSITION_NAMES.get(row["position"], "?")
            avg5 = _fmt_num(row["rolling_avg_fpts_5g"])
            avg10 = _fmt_num(row["rolling_avg_fpts_10g"])
            flag = " INJ" if row["injury_flag"] else ""
            print(
                f"{i:<5} {row['player_name']:<26} {pos:<4} "
                f"{row['projected_fpts']:>6.1f}  {avg5:>6}  {avg10:>6}  "
                f"{_gw_label(row['salary']):>7}  {row['notes'] or ''}{flag}"
            )
        return 0

    if args.command == "recommend-lineup":
        settings = get_settings()
        backend = args.backend or settings.projection_backend
        model_path = Path(args.ml_model_path).expanduser().resolve() if args.ml_model_path else settings.model_artifact_path
        with connect(settings.database_path) as conn:
            gw_id = _resolve_gameweek(conn, getattr(args, "gameweek", None), prefer_next=True)
            if not gw_id:
                print("No upcoming gameweek found.")
                return 1
            try:
                projections = ProjectionModel(
                    connection=conn,
                    gameweek_id=gw_id,
                    backend=backend,
                    model_artifact_path=model_path,
                ).build()
            except FileNotFoundError as exc:
                print(f"Projection error: {exc}")
                return 1

        if not projections:
            print(f"No fixtures for gameweek_id={gw_id}. Cannot build lineup.")
            return 0

        optimizer = LineupOptimizer(
            gameweek_id=gw_id,
            excluded_player_ids=set(args.exclude or []),
            locked_player_ids=set(args.lock or []),
        )
        lineup = optimizer.optimize(projections)
        if lineup is None:
            print("Not enough eligible players to fill all slots.")
            return 1

        print(
            f"\nDoporučená sestava pro kolo {gw_id}  "
            f"(backend: {backend}, proj. body: {lineup['total_fpts']:.1f}, "
            f"cena: {_gw_label(lineup['total_salary'])})\n"
        )
        print(f"{'Slot':<6} {'Hráč':<26} {'Pos':<4} {'Proj':>6}  {'Cena':>7}")
        print("-" * 60)
        for s in lineup["slots"]:
            pos = POSITION_NAMES.get(s["position"], "?")
            print(
                f"{s['slot']:<6} {s['full_name']:<26} {pos:<4} "
                f"{s['projected_fpts']:>6.1f}  {_gw_label(s['salary']):>7}"
            )
        return 0

    if args.command == "evaluate":
        settings = get_settings()
        model_path = Path(args.ml_model_path).expanduser().resolve() if args.ml_model_path else settings.model_artifact_path
        with connect(settings.database_path) as conn:
            gw_id = _resolve_gameweek(conn, getattr(args, "gameweek", None))
            if not gw_id:
                print("Gameweek not found.")
                return 1
            summary = ProjectionEvaluator(connection=conn, gameweek_id=gw_id).evaluate(
                model_artifact_path=model_path
            )

        if summary["evaluated_players"] == 0:
            print(f"No stored projections for gameweek_id={gw_id}.")
        else:
            print(
                f"Evaluace pro gameweek_id={gw_id} (stored backend={summary['backend']}): "
                f"hráčů={summary['evaluated_players']} "
                f"MAE={_fmt_num(summary['mae'])} "
                f"RMSE={_fmt_num(summary['rmse'])} "
                f"BIAS={_fmt_num(summary['bias'])} "
                f"LINEUP_DELTA={_fmt_num(summary['lineup_delta_actual_fpts'])} "
                f"MISS_RATE={_fmt_num((summary['missing_history_rate'] or 0) * 100)}%"
            )
        if summary["backend_comparisons"]:
            print(f"\n{'Backend':<10} {'Hráčů':>6}  {'MAE':>6}  {'RMSE':>6}  {'Bias':>6}  {'Delta':>7}")
            print("-" * 58)
            for row in summary["backend_comparisons"]:
                print(
                    f"{row['backend']:<10} {row['evaluated_players']:>6}  "
                    f"{_fmt_num(row['mae']):>6}  {_fmt_num(row['rmse']):>6}  {_fmt_num(row['bias']):>6}  "
                    f"{_fmt_num(row['lineup_delta_actual_fpts']):>7}"
                )
        return 0

    if args.command == "evaluate-report":
        settings = get_settings()
        with connect(settings.database_path) as conn:
            gw_id = _resolve_gameweek(conn, None)
            rows = ProjectionEvaluator(
                connection=conn, gameweek_id=gw_id or 0
            ).report(days=getattr(args, "rows", 10))

        if not rows:
            print("Žádná evaluace. Spusť nejprve 'evaluate'.")
            return 0
        print(f"\n{'Kolo':<20} {'Hráčů':>6}  {'MAE':>6}  {'RMSE':>6}  {'Bias':>6}  {'Delta':>7}  {'Miss%':>6}")
        print("-" * 76)
        for r in rows:
            print(
                f"{r['gw_name']:<20} {r['evaluated_players']:>6}  "
                f"{_fmt_num(r['mae']):>6}  {_fmt_num(r['rmse']):>6}  {_fmt_num(r['bias']):>6}  "
                f"{_fmt_num(r.get('lineup_delta_actual_fpts')):>7}  {_fmt_num((r.get('missing_history_rate') or 0) * 100):>6}"
            )
        return 0

    if args.command == "explain-lineup-ai":
        settings = get_settings()
        with connect(settings.database_path) as conn:
            gw_id = _resolve_gameweek(conn, getattr(args, "gameweek", None), prefer_next=True)
            if not gw_id:
                print("Kolo nenalezeno.")
                return 1
            model_name = getattr(args, "model", None) or settings.ollama_model
            service = LocalAIService(
                connection=conn,
                ollama_client=OllamaClient(
                    base_url=settings.ollama_base_url,
                    model=model_name,
                    timeout_seconds=settings.ollama_timeout_seconds,
                ),
            )
            try:
                answer = service.explain_lineup(gw_id)
            except OllamaError as exc:
                print(f"Local AI error: {exc}")
                print("Tip: spusť 'ollama serve' a 'ollama pull <model>'.")
                return 1
        print(answer)
        return 0

    if args.command == "ask-ai":
        settings = get_settings()
        with connect(settings.database_path) as conn:
            gw_id = _resolve_gameweek(conn, getattr(args, "gameweek", None), prefer_next=True)
            if not gw_id:
                print("Kolo nenalezeno.")
                return 1
            model_name = getattr(args, "model", None) or settings.ollama_model
            service = LocalAIService(
                connection=conn,
                ollama_client=OllamaClient(
                    base_url=settings.ollama_base_url,
                    model=model_name,
                    timeout_seconds=settings.ollama_timeout_seconds,
                ),
            )
            try:
                answer = service.answer_question(gw_id, args.question)
            except OllamaError as exc:
                print(f"Local AI error: {exc}")
                return 1
        print(answer)
        return 0

    print(f"Příkaz '{args.command}' není implementován.")
    return 1
