from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from medaudit_diff_watcher.repository import DiffRepository


class RepositoryQueryListTests(unittest.TestCase):
    def test_list_batches_jobs_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "repo.db"
            repo = DiffRepository(str(db_path))

            batch_id = repo.create_batch(
                batch_slug="results-20260225010101",
                trigger_reason="scan_once",
                left_folder="C:/left/v1",
                right_folder="C:/left/v2",
            )
            repo.add_batch_report(batch_id, "batch_index_html", "C:/reports/results-20260225010101/index.html")
            repo.add_batch_report(batch_id, "batch_summary_csv", "C:/reports/results-20260225010101/summary.csv")

            job_id = repo.create_job(
                left_folder="C:/left/v1",
                right_folder="C:/left/v2",
                left_csv_path="C:/left/v1/DM.csv",
                right_csv_path="C:/left/v2/DM.csv",
                trigger_reason="scan_once",
                status="queued",
            )
            repo.link_job_to_batch(job_id, batch_id, "DM")
            repo.update_job_status(job_id, "done")
            repo.add_report(job_id, "detailed_html", "C:/reports/results-20260225010101/DM/detailed_report.html")
            repo.add_report(job_id, "detailed_csv", "C:/reports/results-20260225010101/DM/row_diffs.csv")
            repo.add_report(job_id, "ai_summary_md", "C:/reports/results-20260225010101/DM/ai_summary.md")

            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    INSERT INTO diff_summaries(
                        job_id, total_rows_left, total_rows_right, exact_match_rows, added_rows,
                        deleted_rows, suspected_modified_rows, fuzzy_match_enabled, warnings, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (job_id, 100, 101, 98, 2, 1, 0, 1, "[]", "2026-02-25T00:00:00Z"),
                )
                conn.commit()
            finally:
                conn.close()

            batches = repo.list_batches(limit=10)
            jobs = repo.list_jobs(limit=10, batch_id=batch_id)
            reports = repo.list_reports_for_job(job_id)

            self.assertEqual(len(batches), 1)
            self.assertEqual(batches[0]["id"], batch_id)
            self.assertEqual(batches[0]["job_count"], 1)
            self.assertTrue(str(batches[0]["batch_index_html_path"]).endswith("index.html"))

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0]["id"], job_id)
            self.assertEqual(jobs[0]["file_name"], "DM.csv")
            self.assertEqual(jobs[0]["added_rows"], 2)
            self.assertTrue(str(jobs[0]["detailed_report_path"]).endswith("detailed_report.html"))

            self.assertEqual([r["report_type"] for r in reports], ["detailed_html", "detailed_csv", "ai_summary_md"])


if __name__ == "__main__":
    unittest.main()
