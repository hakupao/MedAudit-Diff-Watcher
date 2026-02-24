from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from medaudit_diff_watcher.models import AISummaryResult, CsvDiffResult
from medaudit_diff_watcher.utils import json_dumps, utc_now_iso


class DiffRepository:
    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = str(Path(sqlite_path).expanduser().resolve())
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _managed_conn(self) -> Any:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._managed_conn() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS compare_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_slug TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    trigger_reason TEXT NOT NULL,
                    left_folder TEXT NOT NULL,
                    right_folder TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary_html_path TEXT,
                    summary_csv_path TEXT,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS compare_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    left_folder TEXT NOT NULL,
                    right_folder TEXT NOT NULL,
                    left_csv_path TEXT NOT NULL,
                    right_csv_path TEXT NOT NULL,
                    left_sha256 TEXT,
                    right_sha256 TEXT,
                    trigger_reason TEXT,
                    error_message TEXT,
                    batch_id INTEGER,
                    report_subdir_name TEXT
                );

                CREATE TABLE IF NOT EXISTS file_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    side TEXT NOT NULL,
                    path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    sha256 TEXT NOT NULL,
                    encoding TEXT,
                    delimiter TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES compare_jobs(id)
                );

                CREATE TABLE IF NOT EXISTS schema_diffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL UNIQUE,
                    added_columns TEXT NOT NULL,
                    removed_columns TEXT NOT NULL,
                    reordered_columns TEXT NOT NULL,
                    left_headers TEXT NOT NULL,
                    right_headers TEXT NOT NULL,
                    column_count_left INTEGER NOT NULL,
                    column_count_right INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES compare_jobs(id)
                );

                CREATE TABLE IF NOT EXISTS diff_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL UNIQUE,
                    total_rows_left INTEGER NOT NULL,
                    total_rows_right INTEGER NOT NULL,
                    exact_match_rows INTEGER NOT NULL,
                    added_rows INTEGER NOT NULL,
                    deleted_rows INTEGER NOT NULL,
                    suspected_modified_rows INTEGER NOT NULL,
                    fuzzy_match_enabled INTEGER NOT NULL,
                    warnings TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES compare_jobs(id)
                );

                CREATE TABLE IF NOT EXISTS row_diffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    row_type TEXT NOT NULL,
                    row_json TEXT,
                    peer_row_json TEXT,
                    confidence REAL,
                    match_group_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES compare_jobs(id)
                );

                CREATE TABLE IF NOT EXISTS cell_diffs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    match_group_id TEXT NOT NULL,
                    column_name TEXT NOT NULL,
                    left_value TEXT,
                    right_value TEXT,
                    confidence REAL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES compare_jobs(id)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    report_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES compare_jobs(id)
                );

                CREATE TABLE IF NOT EXISTS batch_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    batch_id INTEGER NOT NULL,
                    report_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(batch_id) REFERENCES compare_batches(id)
                );

                CREATE TABLE IF NOT EXISTS ai_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL UNIQUE,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    token_usage TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES compare_jobs(id)
                );

                CREATE TABLE IF NOT EXISTS job_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES compare_jobs(id)
                );

                """
            )
            self._ensure_compare_jobs_columns(conn)
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_compare_jobs_hashes ON compare_jobs(left_sha256, right_sha256);
                CREATE INDEX IF NOT EXISTS idx_row_diffs_job_id ON row_diffs(job_id);
                CREATE INDEX IF NOT EXISTS idx_reports_job_id ON reports(job_id);
                CREATE INDEX IF NOT EXISTS idx_compare_jobs_batch_id ON compare_jobs(batch_id);
                CREATE INDEX IF NOT EXISTS idx_batch_reports_batch_id ON batch_reports(batch_id);
                """
            )

    def _ensure_compare_jobs_columns(self, conn: sqlite3.Connection) -> None:
        existing = {str(r[1]) for r in conn.execute("PRAGMA table_info(compare_jobs)")}
        if "batch_id" not in existing:
            conn.execute("ALTER TABLE compare_jobs ADD COLUMN batch_id INTEGER")
        if "report_subdir_name" not in existing:
            conn.execute("ALTER TABLE compare_jobs ADD COLUMN report_subdir_name TEXT")

    def create_job(
        self,
        *,
        left_folder: str,
        right_folder: str,
        left_csv_path: str,
        right_csv_path: str,
        trigger_reason: str,
        status: str = "detected",
    ) -> int:
        now = utc_now_iso()
        with self._managed_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO compare_jobs (
                    status, created_at, left_folder, right_folder, left_csv_path, right_csv_path, trigger_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (status, now, left_folder, right_folder, left_csv_path, right_csv_path, trigger_reason),
            )
            return int(cur.lastrowid)

    def create_batch(
        self,
        *,
        batch_slug: str,
        trigger_reason: str,
        left_folder: str,
        right_folder: str,
        status: str = "running",
    ) -> int:
        now = utc_now_iso()
        with self._managed_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO compare_batches(
                    batch_slug, created_at, trigger_reason, left_folder, right_folder, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (batch_slug, now, trigger_reason, left_folder, right_folder, status),
            )
            return int(cur.lastrowid)

    def update_batch_status(self, batch_id: int, status: str, *, error_message: str | None = None) -> None:
        params: list[Any] = [status]
        sql = "UPDATE compare_batches SET status = ?"
        if error_message is not None:
            sql += ", error_message = ?"
            params.append(error_message)
        sql += " WHERE id = ?"
        params.append(batch_id)
        with self._managed_conn() as conn:
            conn.execute(sql, tuple(params))

    def set_batch_summary_paths(
        self,
        batch_id: int,
        *,
        summary_html_path: str | None = None,
        summary_csv_path: str | None = None,
    ) -> None:
        fields: list[str] = []
        params: list[Any] = []
        if summary_html_path is not None:
            fields.append("summary_html_path = ?")
            params.append(str(Path(summary_html_path).resolve()))
        if summary_csv_path is not None:
            fields.append("summary_csv_path = ?")
            params.append(str(Path(summary_csv_path).resolve()))
        if not fields:
            return
        params.append(batch_id)
        with self._managed_conn() as conn:
            conn.execute(f"UPDATE compare_batches SET {', '.join(fields)} WHERE id = ?", tuple(params))

    def link_job_to_batch(self, job_id: int, batch_id: int, report_subdir_name: str) -> None:
        with self._managed_conn() as conn:
            conn.execute(
                "UPDATE compare_jobs SET batch_id = ?, report_subdir_name = ? WHERE id = ?",
                (batch_id, report_subdir_name, job_id),
            )

    def update_job_status(self, job_id: int, status: str, *, error_message: str | None = None) -> None:
        now = utc_now_iso()
        started_at_clause = "started_at = COALESCE(started_at, ?)," if status in {"queued", "comparing"} else ""
        finished = status in {"done", "failed", "reported_done_ai_failed", "duplicate_skipped"}
        params: list[Any] = []
        if started_at_clause:
            params.append(now)
        params.extend([status])
        sql = f"UPDATE compare_jobs SET {started_at_clause} status = ?"
        if error_message is not None:
            sql += ", error_message = ?"
            params.append(error_message)
        if finished:
            sql += ", finished_at = ?"
            params.append(now)
        sql += " WHERE id = ?"
        params.append(job_id)
        with self._managed_conn() as conn:
            conn.execute(sql, tuple(params))

    def set_job_hashes(self, job_id: int, left_sha256: str, right_sha256: str) -> None:
        with self._managed_conn() as conn:
            conn.execute(
                "UPDATE compare_jobs SET left_sha256 = ?, right_sha256 = ? WHERE id = ?",
                (left_sha256, right_sha256, job_id),
            )

    def has_completed_job_for_hashes(self, left_sha256: str, right_sha256: str) -> bool:
        with self._managed_conn() as conn:
            row = conn.execute(
                """
                SELECT id FROM compare_jobs
                WHERE left_sha256 = ? AND right_sha256 = ?
                  AND status IN ('done', 'reported_done_ai_failed')
                LIMIT 1
                """,
                (left_sha256, right_sha256),
            ).fetchone()
            return row is not None

    def log_job(self, job_id: int, level: str, message: str) -> None:
        with self._managed_conn() as conn:
            conn.execute(
                "INSERT INTO job_logs(job_id, level, message, created_at) VALUES (?, ?, ?, ?)",
                (job_id, level.upper(), message, utc_now_iso()),
            )

    def save_diff_result(self, job_id: int, result: CsvDiffResult) -> None:
        now = utc_now_iso()
        with self._managed_conn() as conn:
            conn.executemany(
                """
                INSERT INTO file_snapshots(job_id, side, path, file_size, mtime, sha256, encoding, delimiter, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        job_id,
                        "left",
                        result.left_snapshot.path,
                        result.left_snapshot.file_size,
                        result.left_snapshot.mtime,
                        result.left_snapshot.sha256,
                        result.left_snapshot.encoding,
                        result.left_snapshot.delimiter,
                        now,
                    ),
                    (
                        job_id,
                        "right",
                        result.right_snapshot.path,
                        result.right_snapshot.file_size,
                        result.right_snapshot.mtime,
                        result.right_snapshot.sha256,
                        result.right_snapshot.encoding,
                        result.right_snapshot.delimiter,
                        now,
                    ),
                ],
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO schema_diffs(
                    job_id, added_columns, removed_columns, reordered_columns, left_headers, right_headers,
                    column_count_left, column_count_right, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    json_dumps(result.schema_diff.added_columns),
                    json_dumps(result.schema_diff.removed_columns),
                    json_dumps(result.schema_diff.reordered_columns),
                    json_dumps(result.schema_diff.left_headers),
                    json_dumps(result.schema_diff.right_headers),
                    len(result.schema_diff.left_headers),
                    len(result.schema_diff.right_headers),
                    now,
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO diff_summaries(
                    job_id, total_rows_left, total_rows_right, exact_match_rows, added_rows,
                    deleted_rows, suspected_modified_rows, fuzzy_match_enabled, warnings, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    result.summary.total_rows_left,
                    result.summary.total_rows_right,
                    result.summary.exact_match_rows,
                    result.summary.added_rows,
                    result.summary.deleted_rows,
                    result.summary.suspected_modified_rows,
                    1 if result.summary.fuzzy_match_enabled else 0,
                    json_dumps(result.warnings),
                    now,
                ),
            )
            if result.added_rows:
                conn.executemany(
                    """
                    INSERT INTO row_diffs(job_id, row_type, row_json, peer_row_json, confidence, match_group_id, created_at)
                    VALUES (?, 'added', ?, NULL, NULL, NULL, ?)
                    """,
                    [(job_id, json_dumps(row), now) for row in result.added_rows],
                )
            if result.deleted_rows:
                conn.executemany(
                    """
                    INSERT INTO row_diffs(job_id, row_type, row_json, peer_row_json, confidence, match_group_id, created_at)
                    VALUES (?, 'deleted', ?, NULL, NULL, NULL, ?)
                    """,
                    [(job_id, json_dumps(row), now) for row in result.deleted_rows],
                )
            for row in result.suspected_modified_rows:
                conn.execute(
                    """
                    INSERT INTO row_diffs(job_id, row_type, row_json, peer_row_json, confidence, match_group_id, created_at)
                    VALUES (?, 'suspected_modified', ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        json_dumps(row.left_row),
                        json_dumps(row.right_row),
                        row.confidence,
                        row.match_group_id,
                        now,
                    ),
                )
                if row.cell_diffs:
                    conn.executemany(
                        """
                        INSERT INTO cell_diffs(job_id, match_group_id, column_name, left_value, right_value, confidence, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                job_id,
                                row.match_group_id,
                                cell.column_name,
                                cell.left_value,
                                cell.right_value,
                                row.confidence,
                                now,
                            )
                            for cell in row.cell_diffs
                        ],
                    )

    def add_report(self, job_id: int, report_type: str, file_path: str) -> None:
        with self._managed_conn() as conn:
            conn.execute(
                "INSERT INTO reports(job_id, report_type, file_path, created_at) VALUES (?, ?, ?, ?)",
                (job_id, report_type, str(Path(file_path).resolve()), utc_now_iso()),
            )

    def add_batch_report(self, batch_id: int, report_type: str, file_path: str) -> None:
        with self._managed_conn() as conn:
            conn.execute(
                "INSERT INTO batch_reports(batch_id, report_type, file_path, created_at) VALUES (?, ?, ?, ?)",
                (batch_id, report_type, str(Path(file_path).resolve()), utc_now_iso()),
            )

    def save_ai_summary(self, job_id: int, summary: AISummaryResult) -> None:
        with self._managed_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ai_summaries(job_id, model, prompt_version, summary_text, token_usage, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    summary.model,
                    summary.prompt_version,
                    summary.summary_text,
                    summary.token_usage_json,
                    utc_now_iso(),
                ),
            )

    def get_job(self, job_id: int) -> dict[str, Any] | None:
        with self._managed_conn() as conn:
            row = conn.execute("SELECT * FROM compare_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def get_batch(self, batch_id: int) -> dict[str, Any] | None:
        with self._managed_conn() as conn:
            row = conn.execute("SELECT * FROM compare_batches WHERE id = ?", (batch_id,)).fetchone()
            return dict(row) if row else None

    def fetch_job_bundle(self, job_id: int) -> dict[str, Any]:
        with self._managed_conn() as conn:
            job = conn.execute("SELECT * FROM compare_jobs WHERE id = ?", (job_id,)).fetchone()
            if not job:
                raise KeyError(f"Job not found: {job_id}")
            snapshots = conn.execute(
                "SELECT * FROM file_snapshots WHERE job_id = ? ORDER BY side", (job_id,)
            ).fetchall()
            schema = conn.execute("SELECT * FROM schema_diffs WHERE job_id = ?", (job_id,)).fetchone()
            summary = conn.execute("SELECT * FROM diff_summaries WHERE job_id = ?", (job_id,)).fetchone()
            row_diffs = conn.execute(
                "SELECT * FROM row_diffs WHERE job_id = ? ORDER BY id", (job_id,)
            ).fetchall()
            cell_diffs = conn.execute(
                "SELECT * FROM cell_diffs WHERE job_id = ? ORDER BY id", (job_id,)
            ).fetchall()
            ai_summary = conn.execute("SELECT * FROM ai_summaries WHERE job_id = ?", (job_id,)).fetchone()
            reports = conn.execute("SELECT * FROM reports WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
            batch = None
            batch_reports: list[dict[str, Any]] = []
            job_batch_id = dict(job).get("batch_id")
            if job_batch_id:
                batch_row = conn.execute("SELECT * FROM compare_batches WHERE id = ?", (job_batch_id,)).fetchone()
                if batch_row:
                    batch = dict(batch_row)
                    batch_reports = [
                        dict(r)
                        for r in conn.execute(
                            "SELECT * FROM batch_reports WHERE batch_id = ? ORDER BY id",
                            (job_batch_id,),
                        ).fetchall()
                    ]
            return {
                "job": dict(job),
                "batch": batch,
                "batch_reports": batch_reports,
                "file_snapshots": [dict(r) for r in snapshots],
                "schema_diff": dict(schema) if schema else None,
                "summary": dict(summary) if summary else None,
                "row_diffs": [dict(r) for r in row_diffs],
                "cell_diffs": [dict(r) for r in cell_diffs],
                "ai_summary": dict(ai_summary) if ai_summary else None,
                "reports": [dict(r) for r in reports],
            }
