-- Claude Code Usage Analytics -- warehouse schema v2
--
-- Rebuilt against the ACTUAL company-provided telemetry format
-- (generate_fake_data.py / telemetry_logs.jsonl), which emits 5
-- structurally different event types via OpenTelemetry-style log export.
-- Rather than one sparse table with a `body`/`event_type` discriminator
-- and 20 mostly-NULL columns, each event type gets its own table with
-- only the fields it actually has. All five share the same "envelope"
-- columns (event_id, session_id, user_email, user_id, org_id,
-- terminal_type, timestamp) so cross-type queries still join cleanly.
--
-- See .claude/skills/telemetry-analytics/SKILL.md for query patterns.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS dim_employees (
    email     TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    practice  TEXT NOT NULL,
    level     TEXT NOT NULL,
    location  TEXT NOT NULL
);

-- claude_code.user_prompt
CREATE TABLE IF NOT EXISTS event_user_prompts (
    event_id      TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    user_email    TEXT NOT NULL REFERENCES dim_employees(email),
    user_id       TEXT NOT NULL,
    org_id        TEXT NOT NULL,
    terminal_type TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    prompt_length INTEGER NOT NULL
);

-- claude_code.api_request
CREATE TABLE IF NOT EXISTS event_api_requests (
    event_id            TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    user_email          TEXT NOT NULL REFERENCES dim_employees(email),
    user_id             TEXT NOT NULL,
    org_id              TEXT NOT NULL,
    terminal_type       TEXT NOT NULL,
    timestamp           TEXT NOT NULL,
    model               TEXT NOT NULL,
    input_tokens        INTEGER NOT NULL,
    output_tokens       INTEGER NOT NULL,
    cache_read_tokens   INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL,
    cost_usd            REAL NOT NULL,
    duration_ms         INTEGER NOT NULL
);

-- claude_code.tool_decision
CREATE TABLE IF NOT EXISTS event_tool_decisions (
    event_id      TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    user_email    TEXT NOT NULL REFERENCES dim_employees(email),
    user_id       TEXT NOT NULL,
    org_id        TEXT NOT NULL,
    terminal_type TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    tool_name     TEXT NOT NULL,
    decision      TEXT NOT NULL,   -- 'accept' | 'reject'
    source        TEXT NOT NULL    -- 'config' | 'user_temporary' | 'user_permanent' | 'user_reject'
);

-- claude_code.tool_result
CREATE TABLE IF NOT EXISTS event_tool_results (
    event_id               TEXT PRIMARY KEY,
    session_id             TEXT NOT NULL,
    user_email             TEXT NOT NULL REFERENCES dim_employees(email),
    user_id                TEXT NOT NULL,
    org_id                 TEXT NOT NULL,
    terminal_type          TEXT NOT NULL,
    timestamp               TEXT NOT NULL,
    tool_name              TEXT NOT NULL,
    success                INTEGER NOT NULL,   -- 0/1
    duration_ms            INTEGER NOT NULL,
    decision_source        TEXT,
    decision_type          TEXT,
    tool_result_size_bytes INTEGER
);

-- claude_code.api_error
CREATE TABLE IF NOT EXISTS event_api_errors (
    event_id      TEXT PRIMARY KEY,
    session_id    TEXT NOT NULL,
    user_email    TEXT NOT NULL REFERENCES dim_employees(email),
    user_id       TEXT NOT NULL,
    org_id        TEXT NOT NULL,
    terminal_type TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    error_message TEXT NOT NULL,
    status_code   TEXT,
    model         TEXT NOT NULL,
    duration_ms   INTEGER NOT NULL,
    attempt       INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prompts_session ON event_user_prompts(session_id);
CREATE INDEX IF NOT EXISTS idx_prompts_email ON event_user_prompts(user_email);
CREATE INDEX IF NOT EXISTS idx_prompts_ts ON event_user_prompts(timestamp);

CREATE INDEX IF NOT EXISTS idx_requests_session ON event_api_requests(session_id);
CREATE INDEX IF NOT EXISTS idx_requests_email ON event_api_requests(user_email);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON event_api_requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_requests_model ON event_api_requests(model);

CREATE INDEX IF NOT EXISTS idx_decisions_session ON event_tool_decisions(session_id);
CREATE INDEX IF NOT EXISTS idx_decisions_email ON event_tool_decisions(user_email);
CREATE INDEX IF NOT EXISTS idx_decisions_tool ON event_tool_decisions(tool_name);

CREATE INDEX IF NOT EXISTS idx_results_session ON event_tool_results(session_id);
CREATE INDEX IF NOT EXISTS idx_results_email ON event_tool_results(user_email);
CREATE INDEX IF NOT EXISTS idx_results_tool ON event_tool_results(tool_name);

CREATE INDEX IF NOT EXISTS idx_errors_session ON event_api_errors(session_id);
CREATE INDEX IF NOT EXISTS idx_errors_email ON event_api_errors(user_email);

-- Session-level rollup, derived from whichever event tables have data for
-- that session_id. A VIEW rather than a materialized table -- one source
-- of truth, always in sync, and the data volume is small enough that
-- recomputing it per query is not a real cost in SQLite.
CREATE VIEW IF NOT EXISTS session_summary AS
WITH all_session_events AS (
    SELECT session_id, user_email, timestamp FROM event_user_prompts
    UNION ALL
    SELECT session_id, user_email, timestamp FROM event_api_requests
    UNION ALL
    SELECT session_id, user_email, timestamp FROM event_tool_decisions
    UNION ALL
    SELECT session_id, user_email, timestamp FROM event_tool_results
    UNION ALL
    SELECT session_id, user_email, timestamp FROM event_api_errors
)
SELECT
    session_id,
    user_email,
    MIN(timestamp) AS start_time,
    MAX(timestamp) AS end_time,
    COUNT(*) AS event_count,
    (julianday(MAX(timestamp)) - julianday(MIN(timestamp))) * 24 * 60 AS duration_minutes
FROM all_session_events
GROUP BY session_id, user_email;

CREATE TABLE IF NOT EXISTS ingestion_log (
    run_id        TEXT NOT NULL,
    run_time      TEXT NOT NULL,
    source_file   TEXT NOT NULL,
    rows_read     INTEGER NOT NULL,
    rows_loaded   INTEGER NOT NULL,
    rows_dropped  INTEGER NOT NULL,
    rows_repaired INTEGER NOT NULL,
    notes         TEXT
);
