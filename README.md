# Fantasy Premier League AI Helper

Lokální nástroj pro doporučování sestavy ve Fantasy Premier League (česká varianta bodování).  
Používá veřejné FPL API, SQLite databázi, deterministický scoring engine, volitelný ML projekční model a lokální LLM (Ollama) pro vysvětlení výběru.

---

## Funkce

- Stahuje aktuální data z FPL API (hráči, týmy, herní kola, výsledky)
- Počítá fantasy body podle **českých bodovacích tabulek** (viz [`fantasy-bodovani-fotbal.md`](fantasy-bodovani-fotbal.md))
- Projektuje výkon hráčů na základě historického průměru, obtížnosti zápasu a pravděpodobnosti výhry týmu
- Umí natrénovat ML model z historických gameweeků a použít ho místo baseline projekce
- Ukládá per-gameweek feature snapshoty pro stabilní trénink a pozdější benchmarking
- Umí po odehraném kole porovnat `baseline` a `ml` backend na stejných snapshot datech
- Sestavuje optimální 11 hráčů (1 GK + 10 pole) v rámci rozpočtu £100M
- Nabízí CLI, REST API a volitelné AI vysvětlení prostřednictvím lokálního modelu (Ollama / llama3.1:8b)

---

## Požadavky

- Python 3.11+
- [Ollama](https://ollama.com) s modelem `llama3.1:8b` (pouze pro AI příkazy)

```bash
ollama pull llama3.1:8b
```

---

## Instalace

```bash
git clone <url>
cd fantasy-pm-ai-helper
pip install -e ".[dev]"
```

---

## Rychlý start

```bash
# Stáhni data, přepočítej projekce a zobraz sestavu v jednom kroku:
./run_today.sh

# Nebo krok po kroku:
fantasy-pl update-data
fantasy-pl rebuild-projections
fantasy-pl recommend-lineup

# ML varianta:
fantasy-pl train-ml-model
fantasy-pl rebuild-projections --backend ml
fantasy-pl recommend-lineup --backend ml
```

---

## CLI příkazy

| Příkaz | Popis |
|---|---|
| `update-data` | Stáhne aktuální data z FPL API do lokální SQLite databáze |
| `train-ml-model [--upto-gameweek ID] [--output cesta.pkl]` | Natrénuje ML model z historických gameweeků |
| `rebuild-projections [--gameweek N] [--backend baseline\|ml] [--ml-model-path cesta.pkl]` | Přepočítá projekce bodů pro dané kolo |
| `recommend-lineup [--gameweek N] [--exclude ID…] [--lock ID…] [--backend baseline\|ml]` | Sestaví doporučených 11 hráčů |
| `show-projections [--gameweek N] [--top N] [--position 1-4]` | Zobrazí top projekce |
| `evaluate [--gameweek N] [--ml-model-path cesta.pkl]` | Porovná uložené projekce se skutečnými body a zároveň ukáže `baseline vs ml` benchmark |
| `evaluate-report [--rows N]` | Historický přehled přesnosti uložených projekcí |
| `explain-lineup-ai [--gameweek N] [--model M]` | LLM vysvětlení sestavy |
| `ask-ai "otázka" [--gameweek N] [--model M]` | Libovolný dotaz na LLM |

---

## REST API

Spuštění serveru:

```bash
fantasy-pl-api
# nebo
uvicorn "fantasy_pl_ai_helper.api.app:create_app" --factory --port 8000
```

Dokumentace (Swagger UI): [http://localhost:8000/docs](http://localhost:8000/docs)

### Hlavní endpointy

| Metoda | URL | Popis |
|---|---|---|
| `GET` | `/health` | Status serveru |
| `POST` | `/v1/data/update` | Stáhne aktuální data |
| `GET` | `/v1/gameweeks/current` | Aktuální herní kolo |
| `GET` | `/v1/gameweeks/{id}/projections?rebuild=true&top=50` | Projekce hráčů |
| `GET` | `/v1/gameweeks/{id}/lineup?exclude=5&lock=3` | Doporučená sestava |
| `POST` | `/v1/gameweeks/{id}/evaluate` | Vyhodnocení projekcí |
| `GET` | `/v1/evaluations/report` | Historický přehled |

---

## Bodování

Bodování vychází z [`fantasy-bodovani-fotbal.md`](fantasy-bodovani-fotbal.md).

| Událost | GK | DEF | MID | FWD |
|---|---|---|---|---|
| Gól | 30 | 24 | 18 | 12 |
| Asistence | 15 | 12 | 8 | 6 |
| Čisté konto | 3 | 2 | 1 | 1 |
| Zákrok (GK) | 3 | – | – | – |
| Penalta chycena | 8 | – | – | – |
| Obdržený gól | −3 | – | – | – |
| Výhra | +2 | +2 | +2 | +2 |
| Remíza | +1 | +1 | +1 | +1 |
| Prohra | −2 | −2 | −2 | −2 |
| Každých 20 min | +1 | +1 | +1 | +1 |
| Žlutá karta | −2 | −2 | −2 | −2 |
| Červená karta | −5 | −5 | −5 | −5 |
| Vlastní gól | −5 | −5 | −5 | −5 |
| Penalta neproměněna | −4 | −4 | −4 | −4 |

> **Poznámka:** FPL API neposkytuje střely, souboje, driblinky, přihrávky do šance ani rohy — tyto statistiky jsou v aktuální verzi bodovány jako 0.

---

## Formace sestavy

Povolené formace (DEF–MID–FWD):  
4-4-2 · 4-3-3 · 3-5-2 · 3-4-3 · 5-4-1 · 5-3-2 · 4-5-1 · 3-3-4 · 4-2-4 · 5-2-3

Vždy 1 brankář + 10 hráčů pole. Celkový rozpočet ≤ £100M.

---

## Architektura

```
src/fantasy_pl_ai_helper/
├── config.py               # Settings
├── ingest/
│   ├── fpl_client.py       # HTTP klient pro FPL API
│   └── service.py          # Stahování a ukládání dat
├── storage/
│   ├── schema.sql          # SQLite schéma
│   ├── database.py         # Připojení k DB
│   └── init_db.py          # Inicializace DB
├── scoring/
│   └── engine.py           # Deterministický scoring engine
├── features/
│   └── pipeline.py         # Výpočet příznaků (průměry, win-prob)
├── models/
│   ├── projections.py      # Projekční model + feature snapshot persistence
│   ├── ml.py               # Trénování a inference ML modelu
│   └── evaluation.py       # Evaluace a baseline-vs-ML benchmarking
├── optimizer/
│   └── lineup.py           # Greedy lineup optimizer
├── ai/
│   ├── ollama.py           # Ollama HTTP klient
│   └── explanations.py     # LocalAIService
├── api/
│   ├── contracts.py        # Pydantic response modely
│   └── app.py              # FastAPI aplikace
└── cli/
    └── main.py             # CLI (argparse)
```

---

## Proměnné prostředí

| Proměnná | Výchozí | Popis |
|---|---|---|
| `FANTASY_PL_PROJECT_ROOT` | adresář projektu | Kořenový adresář projektu |
| `FANTASY_PL_DATABASE_PATH` | `<root>/data/fantasy_pl.sqlite3` | Cesta k SQLite souboru |
| `FANTASY_PL_PROJECTION_BACKEND` | `baseline` | Výchozí projekční backend |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | URL Ollama serveru |
| `OLLAMA_MODEL` | `llama3.1:8b` | Název modelu |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Timeout pro AI požadavky |

---

## Testy

```bash
pytest tests/ -v
```
