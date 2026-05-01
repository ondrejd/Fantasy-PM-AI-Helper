-- Fantasy Premier League AI Helper — SQLite schema
-- Positions: GK=1, DEF=2, MID=3, FWD=4

-- ---------------------------------------------------------------------------
-- Seasons
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS seasons (
    id              INTEGER PRIMARY KEY,
    fpl_season_id   TEXT    NOT NULL UNIQUE,  -- e.g. "2526" for 2025/26
    season_label    TEXT    NOT NULL,          -- e.g. "2025/26"
    is_current      INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Teams
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teams (
    id              INTEGER PRIMARY KEY,
    fpl_team_id     INTEGER NOT NULL UNIQUE,
    full_name       TEXT    NOT NULL,
    short_name      TEXT,
    logo_url        TEXT,
    logo            BLOB,
    strength_overall_home   INTEGER,
    strength_overall_away   INTEGER,
    strength_attack_home    INTEGER,
    strength_attack_away    INTEGER,
    strength_defence_home   INTEGER,
    strength_defence_away   INTEGER,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Players
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS players (
    id              INTEGER PRIMARY KEY,
    fpl_player_id   INTEGER NOT NULL UNIQUE,
    full_name       TEXT    NOT NULL,
    first_name      TEXT,
    last_name       TEXT,
    -- Position: GK=1, DEF=2, MID=3, FWD=4
    position        INTEGER NOT NULL,
    team_id         INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    -- Price in £0.1M units (e.g. 90 = £9.0M)
    now_cost        INTEGER NOT NULL DEFAULT 0,
    status          TEXT,   -- 'a'=available, 'd'=doubtful, 'i'=injured, 's'=suspended, 'u'=unavailable, 'n'=not in squad
    chance_of_playing_next_round INTEGER,
    is_active       INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Gameweeks (events in FPL)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gameweeks (
    id              INTEGER PRIMARY KEY,
    fpl_event_id    INTEGER NOT NULL UNIQUE,
    season_id       INTEGER NOT NULL REFERENCES seasons(id),
    name            TEXT    NOT NULL,   -- e.g. "Gameweek 35"
    deadline_time   TEXT,
    average_entry_score INTEGER,
    is_current      INTEGER NOT NULL DEFAULT 0,
    is_next         INTEGER NOT NULL DEFAULT 0,
    finished        INTEGER NOT NULL DEFAULT 0,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Fixtures
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixtures (
    id              INTEGER PRIMARY KEY,
    fpl_fixture_id  INTEGER NOT NULL UNIQUE,
    gameweek_id     INTEGER REFERENCES gameweeks(id),
    season_id       INTEGER NOT NULL REFERENCES seasons(id),
    kickoff_time    TEXT,
    home_team_id    INTEGER NOT NULL REFERENCES teams(id),
    away_team_id    INTEGER NOT NULL REFERENCES teams(id),
    started         INTEGER NOT NULL DEFAULT 0,
    finished        INTEGER NOT NULL DEFAULT 0,
    finished_provisional INTEGER NOT NULL DEFAULT 0,
    home_score      INTEGER,
    away_score      INTEGER,
    -- Difficulty ratings (1-5, 1=easiest)
    home_difficulty INTEGER,
    away_difficulty INTEGER,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Player game logs (per-fixture performance)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_game_logs (
    id                  INTEGER PRIMARY KEY,
    player_id           INTEGER NOT NULL REFERENCES players(id),
    fixture_id          INTEGER NOT NULL REFERENCES fixtures(id),
    team_id             INTEGER REFERENCES teams(id),
    opponent_team_id    INTEGER REFERENCES teams(id),
    was_home            INTEGER NOT NULL DEFAULT 0,
    minutes             INTEGER NOT NULL DEFAULT 0,
    goals_scored        INTEGER NOT NULL DEFAULT 0,
    assists             INTEGER NOT NULL DEFAULT 0,
    clean_sheets        INTEGER NOT NULL DEFAULT 0,
    goals_conceded      INTEGER NOT NULL DEFAULT 0,
    own_goals           INTEGER NOT NULL DEFAULT 0,
    penalties_saved     INTEGER NOT NULL DEFAULT 0,
    penalties_missed    INTEGER NOT NULL DEFAULT 0,
    yellow_cards        INTEGER NOT NULL DEFAULT 0,
    red_cards           INTEGER NOT NULL DEFAULT 0,
    saves               INTEGER NOT NULL DEFAULT 0,
    bonus               INTEGER NOT NULL DEFAULT 0,
    bps                 INTEGER NOT NULL DEFAULT 0,
    -- xStats from FPL (useful as projection features)
    expected_goals      REAL,
    expected_assists    REAL,
    expected_goals_conceded REAL,
    influence           REAL,
    creativity          REAL,
    threat              REAL,
    -- Calculated by ingest: W/D/L
    result_type         TEXT,   -- 'W','D','L'
    -- FPL official points (for reference / validation)
    fpl_total_points    INTEGER NOT NULL DEFAULT 0,
    raw_payload         TEXT,
    UNIQUE(player_id, fixture_id)
);

-- ---------------------------------------------------------------------------
-- Betting odds (per-fixture pre-match probabilities)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixture_odds (
    id                INTEGER PRIMARY KEY,
    fixture_id        INTEGER NOT NULL REFERENCES fixtures(id),
    provider          TEXT    NOT NULL,
    bookmaker         TEXT,
    home_win_prob     REAL,
    draw_prob         REAL,
    away_win_prob     REAL,
    home_decimal_odds REAL,
    draw_decimal_odds REAL,
    away_decimal_odds REAL,
    fetched_at        TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(fixture_id, provider)
);

-- ---------------------------------------------------------------------------
-- Player projections (per gameweek)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_projections (
    id              INTEGER PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(id),
    gameweek_id     INTEGER NOT NULL REFERENCES gameweeks(id),
    backend         TEXT    NOT NULL DEFAULT 'baseline',
    position        INTEGER NOT NULL,
    salary          INTEGER NOT NULL DEFAULT 0,  -- now_cost snapshot
    projected_fpts  REAL    NOT NULL DEFAULT 0,
    rolling_avg_fpts_5g  REAL,
    rolling_avg_fpts_10g REAL,
    games_in_window INTEGER NOT NULL DEFAULT 0,
    injury_flag     INTEGER NOT NULL DEFAULT 0,
    fixture_difficulty INTEGER,  -- 1-5
    team_win_prob   REAL,
    notes           TEXT,
    built_at        TEXT    NOT NULL,
    -- Evaluation columns (filled after GW finishes)
    actual_fpts     REAL,
    abs_error       REAL,
    sq_error        REAL,
    evaluated_at    TEXT,
    UNIQUE(player_id, gameweek_id)
);

-- ---------------------------------------------------------------------------
-- Player feature snapshots (stored per gameweek build)
-- ---------------------------------------------------------------------------
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
);

-- ---------------------------------------------------------------------------
-- Projection evaluations (per-gameweek summary)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projection_evaluations (
    id              INTEGER PRIMARY KEY,
    gameweek_id     INTEGER NOT NULL REFERENCES gameweeks(id),
    evaluated_players INTEGER NOT NULL DEFAULT 0,
    mae             REAL,
    rmse            REAL,
    bias            REAL,
    lineup_delta_actual_fpts REAL,
    missing_history_players INTEGER NOT NULL DEFAULT 0,
    missing_history_rate REAL,
    created_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- Injuries / availability
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS injuries (
    id              INTEGER PRIMARY KEY,
    player_id       INTEGER NOT NULL REFERENCES players(id),
    injury_status   TEXT,   -- 'doubtful', 'injured', 'suspended'
    news            TEXT,
    chance_of_playing_next_round INTEGER,
    is_active       INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(player_id)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);
CREATE INDEX IF NOT EXISTS idx_fixtures_gw ON fixtures(gameweek_id);
CREATE INDEX IF NOT EXISTS idx_logs_player ON player_game_logs(player_id);
CREATE INDEX IF NOT EXISTS idx_logs_fixture ON player_game_logs(fixture_id);
CREATE INDEX IF NOT EXISTS idx_projections_gw ON player_projections(gameweek_id);
CREATE INDEX IF NOT EXISTS idx_fixture_odds_fixture ON fixture_odds(fixture_id);
CREATE INDEX IF NOT EXISTS idx_feature_snapshots_gw ON player_feature_snapshots(gameweek_id);
