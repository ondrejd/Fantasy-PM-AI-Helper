#!/usr/bin/env bash
# run_today.sh — stáhni aktuální data, přepočítej projekce a zobraz doporučenou sestavu
set -euo pipefail

cd "$(dirname "$0")"

# Aktivuj venv pokud existuje
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Spouštěj CLI přes modul, aby skript fungoval i bez pip install -e .
if [ -x ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
else
    PYTHON_BIN="python3"
fi

run_cli() {
    PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m fantasy_pl_ai_helper "$@"
}

echo "=== Fantasy PL AI Helper — $(date '+%Y-%m-%d %H:%M') ==="
echo ""

echo "[1/3] Aktualizace dat z FPL API..."
run_cli update-data
echo ""

echo "[2/3] Přepočet projekcí pro aktuální kolo..."
run_cli rebuild-projections
echo ""

echo "[3/3] Doporučená sestava..."
run_cli recommend-lineup
echo ""

echo "=== Hotovo ==="
