from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from medaudit_diff_watcher.repository import DiffRepository


class RepositoryMigrationTests(unittest.TestCase):
    def test_legacy_compare_jobs_schema_is_upgraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE compare_jobs (
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
                        error_message TEXT
                    );
                    """
                )
                conn.commit()
            finally:
                conn.close()

            repo = DiffRepository(str(db_path))
            self.assertIsNotNone(repo)

            conn = sqlite3.connect(db_path)
            try:
                cols = {row[1] for row in conn.execute("PRAGMA table_info(compare_jobs)")}
                self.assertIn("batch_id", cols)
                self.assertIn("report_subdir_name", cols)
                # Batch index should now be creatable/present.
                indexes = {row[1] for row in conn.execute("PRAGMA index_list(compare_jobs)")}
                self.assertIn("idx_compare_jobs_batch_id", indexes)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()

