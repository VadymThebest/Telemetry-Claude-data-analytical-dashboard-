"""
Ingests the real company-provided telemetry format:
  - employees.csv         (flat CSV)
  - telemetry_logs.jsonl  (one CloudWatch-style log BATCH per line; each
                            batch's logEvents[].message is a JSON string
                            containing the actual event)

Streams the JSONL file line-by-line (it's 200MB+ at realistic scale) and
batches inserts, rather than loading everything into memory at once.

Validation policy (same philosophy as v1): drop a row with a logged
reason, or repair it with a logged reason, never silently guess.
  - user_email must exist in dim_employees -> otherwise dropped as orphan
  - timestamp must be parseable -> otherwise dropped
  - numeric fields (tokens, cost, duration) that fail to parse are
    repaired to 0 and counted separately
  - duplicate event ids (shouldn't occur in this generator, but the
    INSERT OR IGNORE + PRIMARY KEY guards against it defensively)

Run:
    python3 data_pipeline_v2/ingest.py --raw-dir path/to/output --reset
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = ROOT / "data" / "warehouse.db"

BATCH_COMMIT_SIZE = 5000


def _to_int(value, default=0):
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def init_db(conn: sqlite3.Connection, reset: bool):
    if reset:
        conn.executescript("""
            DROP VIEW IF EXISTS session_summary;
            DROP TABLE IF EXISTS event_user_prompts;
            DROP TABLE IF EXISTS event_api_requests;
            DROP TABLE IF EXISTS event_tool_decisions;
            DROP TABLE IF EXISTS event_tool_results;
            DROP TABLE IF EXISTS event_api_errors;
            DROP TABLE IF EXISTS dim_employees;
            DROP TABLE IF EXISTS ingestion_log;
        """)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


def load_employees(conn: sqlite3.Connection, raw_dir: Path, run_id: str) -> set[str]:
    path = raw_dir / "employees.csv"
    if not path.exists():
        raise FileNotFoundError(f"Expected {path}")
    # encoding="utf-8-sig" strips a byte-order-mark if present and is a
    # no-op if it isn't -- safe either way, and this is exactly the kind
    # of write/read encoding mismatch that silently corrupts the header
    # row's first field on some Windows locales.
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
        # Defensive belt-and-suspenders: if a stray BOM character still
        # made it into a fieldname, strip it rather than fail silently.
        if rows and any(k and k.startswith("\ufeff") for k in rows[0].keys()):
            rows = [{k.lstrip("\ufeff"): v for k, v in row.items()} for row in rows]

    if rows and "email" not in rows[0]:
        print(f"    !! WARNING: 'email' column not found. Actual columns: {list(rows[0].keys())}")

    seen: set[str] = set()
    loaded = []
    dropped = 0
    for row in rows:
        email = (row.get("email") or "").strip()
        if not email or email in seen:
            dropped += 1
            continue
        seen.add(email)
        loaded.append((
            email,
            (row.get("full_name") or "unknown").strip(),
            (row.get("practice") or "unknown").strip(),
            (row.get("level") or "unknown").strip(),
            (row.get("location") or "unknown").strip(),
        ))

    conn.executemany(
        "INSERT OR IGNORE INTO dim_employees (email, full_name, practice, level, location) "
        "VALUES (?, ?, ?, ?, ?)",
        loaded,
    )
    conn.commit()
    _log(conn, run_id, "employees.csv", len(rows), len(loaded), dropped, 0,
         "dropped: missing/duplicate email")
    return seen


class TypedBatches:
    """Small helper to accumulate rows per target table and flush in
    fixed-size batches, so we never hold the whole 200MB+ file in memory."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.buffers: dict[str, list[tuple]] = {
            "event_user_prompts": [],
            "event_api_requests": [],
            "event_tool_decisions": [],
            "event_tool_results": [],
            "event_api_errors": [],
        }
        self.insert_sql = {
            "event_user_prompts": (
                "INSERT OR IGNORE INTO event_user_prompts "
                "(event_id, session_id, user_email, user_id, org_id, terminal_type, timestamp, prompt_length) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            "event_api_requests": (
                "INSERT OR IGNORE INTO event_api_requests "
                "(event_id, session_id, user_email, user_id, org_id, terminal_type, timestamp, model, "
                " input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, cost_usd, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            "event_tool_decisions": (
                "INSERT OR IGNORE INTO event_tool_decisions "
                "(event_id, session_id, user_email, user_id, org_id, terminal_type, timestamp, tool_name, decision, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            "event_tool_results": (
                "INSERT OR IGNORE INTO event_tool_results "
                "(event_id, session_id, user_email, user_id, org_id, terminal_type, timestamp, tool_name, success, "
                " duration_ms, decision_source, decision_type, tool_result_size_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            "event_api_errors": (
                "INSERT OR IGNORE INTO event_api_errors "
                "(event_id, session_id, user_email, user_id, org_id, terminal_type, timestamp, error_message, "
                " status_code, model, duration_ms, attempt) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
        }
        self.loaded_counts = {k: 0 for k in self.buffers}

    def add(self, table: str, row: tuple):
        self.buffers[table].append(row)
        if len(self.buffers[table]) >= BATCH_COMMIT_SIZE:
            self._flush(table)

    def _flush(self, table: str):
        rows = self.buffers[table]
        if not rows:
            return
        self.conn.executemany(self.insert_sql[table], rows)
        self.loaded_counts[table] += len(rows)
        self.buffers[table] = []

    def flush_all(self):
        for table in self.buffers:
            self._flush(table)
        self.conn.commit()


def load_events(conn: sqlite3.Connection, raw_dir: Path, run_id: str, valid_emails: set[str]):
    path = raw_dir / "telemetry_logs.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"Expected {path}")

    batches_out = TypedBatches(conn)
    seen_event_ids: set[str] = set()

    rows_read = 0
    dropped_orphan_email = 0
    dropped_bad_json = 0
    dropped_missing_ts = 0
    dropped_duplicate = 0
    repaired_numeric = 0

    t0 = time.time()
    with path.open() as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                batch = json.loads(line)
            except json.JSONDecodeError:
                dropped_bad_json += 1
                continue

            for log_event in batch.get("logEvents", []):
                rows_read += 1
                try:
                    msg = json.loads(log_event["message"])
                except (KeyError, json.JSONDecodeError, TypeError):
                    dropped_bad_json += 1
                    continue

                body = msg.get("body", "")
                attrs = msg.get("attributes", {})

                user_email = (attrs.get("user.email") or "").strip()
                session_id = (attrs.get("session.id") or "").strip()
                ts = (attrs.get("event.timestamp") or "").strip()

                if user_email not in valid_emails:
                    dropped_orphan_email += 1
                    continue
                if not ts:
                    dropped_missing_ts += 1
                    continue
                if not session_id:
                    dropped_missing_ts += 1  # malformed row, same bucket
                    continue

                event_id = str(log_event.get("id") or uuid.uuid4())
                if event_id in seen_event_ids:
                    dropped_duplicate += 1
                    continue
                seen_event_ids.add(event_id)

                user_id = attrs.get("user.id", "")
                org_id = attrs.get("organization.id", "")
                terminal_type = attrs.get("terminal.type", "")

                common = (event_id, session_id, user_email, user_id, org_id, terminal_type, ts)

                if body == "claude_code.user_prompt":
                    prompt_length = _to_int(attrs.get("prompt_length"), default=None)
                    if prompt_length is None:
                        prompt_length = 0
                        repaired_numeric += 1
                    batches_out.add("event_user_prompts", common + (prompt_length,))

                elif body == "claude_code.api_request":
                    row = common + (
                        attrs.get("model", "unknown"),
                        _to_int(attrs.get("input_tokens")),
                        _to_int(attrs.get("output_tokens")),
                        _to_int(attrs.get("cache_read_tokens")),
                        _to_int(attrs.get("cache_creation_tokens")),
                        _to_float(attrs.get("cost_usd")),
                        _to_int(attrs.get("duration_ms")),
                    )
                    batches_out.add("event_api_requests", row)

                elif body == "claude_code.tool_decision":
                    row = common + (
                        attrs.get("tool_name", "unknown"),
                        attrs.get("decision", "unknown"),
                        attrs.get("source", "unknown"),
                    )
                    batches_out.add("event_tool_decisions", row)

                elif body == "claude_code.tool_result":
                    success_raw = str(attrs.get("success", "false")).strip().lower()
                    success = 1 if success_raw == "true" else 0
                    row = common + (
                        attrs.get("tool_name", "unknown"),
                        success,
                        _to_int(attrs.get("duration_ms")),
                        attrs.get("decision_source"),
                        attrs.get("decision_type"),
                        _to_int(attrs.get("tool_result_size_bytes"), default=None),
                    )
                    batches_out.add("event_tool_results", row)

                elif body == "claude_code.api_error":
                    row = common + (
                        attrs.get("error", "unknown"),
                        attrs.get("status_code"),
                        attrs.get("model", "unknown"),
                        _to_int(attrs.get("duration_ms")),
                        _to_int(attrs.get("attempt"), default=1),
                    )
                    batches_out.add("event_api_errors", row)

                else:
                    # Unknown event body -- don't silently swallow, but
                    # don't crash the whole ingestion either.
                    dropped_bad_json += 1

            if line_no % 5000 == 0:
                print(f"    ...{line_no} batches / {rows_read} events processed "
                      f"({time.time() - t0:.1f}s elapsed)")

    batches_out.flush_all()
    elapsed = time.time() - t0

    total_loaded = sum(batches_out.loaded_counts.values())
    total_dropped = dropped_orphan_email + dropped_bad_json + dropped_missing_ts + dropped_duplicate

    print(f"    Loaded by type: {batches_out.loaded_counts}")
    _log(conn, run_id, "telemetry_logs.jsonl", rows_read, total_loaded, total_dropped, repaired_numeric,
         f"dropped: orphan_email={dropped_orphan_email} bad_json={dropped_bad_json} "
         f"missing_ts_or_session={dropped_missing_ts} duplicate={dropped_duplicate}; "
         f"repaired: numeric_fields={repaired_numeric}; ingest_time_s={elapsed:.1f}")


def _log(conn, run_id, source_file, rows_read, rows_loaded, rows_dropped, rows_repaired, notes):
    conn.execute(
        "INSERT INTO ingestion_log (run_id, run_time, source_file, rows_read, rows_loaded, "
        "rows_dropped, rows_repaired, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, datetime.now(timezone.utc).isoformat(), source_file,
         rows_read, rows_loaded, rows_dropped, rows_repaired, notes),
    )
    conn.commit()
    print(f"[{source_file}] read={rows_read} loaded={rows_loaded} "
          f"dropped={rows_dropped} repaired={rows_repaired}")


def run(raw_dir: Path, db_path: Path, reset: bool):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    # perf pragmas -- safe for a local single-writer batch load
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    run_id = str(uuid.uuid4())[:8]
    try:
        init_db(conn, reset=reset)
        valid_emails = load_employees(conn, raw_dir, run_id)
        load_events(conn, raw_dir, run_id, valid_emails)
        print(f"Done. Warehouse at {db_path} (run_id={run_id})")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=str, required=True,
                         help="Directory containing employees.csv and telemetry_logs.jsonl")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH))
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    run(Path(args.raw_dir), Path(args.db), reset=args.reset)


if __name__ == "__main__":
    main()
