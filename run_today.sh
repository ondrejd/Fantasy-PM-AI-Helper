#!/usr/bin/env bash
# run_today.sh — stáhni aktuální data, přepočítej projekce a zobraz doporučenou sestavu
set -euo pipefail

cd "$(dirname "$0")"

# Aktivuj venv pokud existuje
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

echo "=== Fantasy PL AI Helper — $(date '+%Y-%m-%d %H:%M') ==="
echo ""

echo "[1/3] Aktualizace dat z FPL API..."
fantasy-pl update-data
echo ""

echo "[2/3] Přepočet projekcí pro aktuální kolo..."
fantasy-pl rebuild-projections
echo ""

echo "[3/3] Doporučená sestava..."
fantasy-pl recommend-lineup
echo ""

echo "=== Hotovo ==="
