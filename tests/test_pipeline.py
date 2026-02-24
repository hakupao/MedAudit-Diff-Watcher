from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from medaudit_diff_watcher.ai_client import AISummaryClient
from medaudit_diff_watcher.compare_tool_launcher import CompareToolLauncher
from medaudit_diff_watcher.config import (
    AIConfig,
    AppConfig,
    CompareToolConfig,
    CsvConfig,
    DBConfig,
    DiffConfig,
    LoggingConfig,
    PairingConfig,
    ReportConfig,
    WatchConfig,
)
from medaudit_diff_watcher.csv_diff import CsvDiffEngine
from medaudit_diff_watcher.pipeline import PipelineRunner
from medaudit_diff_watcher.planner import JobPlanner
from medaudit_diff_watcher.reporting import DetailedReportRenderer
from medaudit_diff_watcher.repository import DiffRepository
from medaudit_diff_watcher.models import AISummaryResult


class _StubBatchAISummaryClient(AISummaryClient):
    def generate_summary(self, result):  # type: ignore[override]
        return AISummaryResult(
            summary_text="# File AI Summary\n\nstub",
            model="stub-model",
            prompt_version="stub_file_v1",
            token_usage_json="{}",
        )

    def generate_batch_summary(self, *, batch_meta, file_rows):  # type: ignore[override]
        return AISummaryResult(
            summary_text="# Batch AI Summary\n\nstub",
            model="stub-model",
            prompt_version="stub_batch_v1",
            token_usage_json="{}",
        )


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.left = self.root / "batch_001"
        self.right = self.root / "batch_002"
        self.left.mkdir()
        self.right.mkdir()
        (self.left / "result.csv").write_text("id,name,score\n1,Alice,10\n2,Bob,20\n", encoding="utf-8", newline="")
        (self.right / "result.csv").write_text(
            "id,name,score\n1,Alice,10\n2,Bob,25\n3,Carol,30\n",
            encoding="utf-8",
            newline="",
        )

        self.config = AppConfig(
            watch=WatchConfig(root_dir=str(self.root), scan_interval_sec=1, stable_wait_sec=1),
            pairing=PairingConfig(strategy="latest_two"),
            csv=CsvConfig(fixed_filename="result.csv"),
            diff=DiffConfig(enable_fuzzy_match=True, fuzzy_threshold=80, max_fuzzy_comparisons=10000),
            compare_tool=CompareToolConfig(enabled=False, executable_path=""),
            db=DBConfig(sqlite_path=str(self.root / "data" / "medaudit.db")),
            report=ReportConfig(output_dir=str(self.root / "reports")),
            ai=AIConfig(enabled=False),
            logging=LoggingConfig(level="INFO"),
        )
        self.config.ensure_runtime_dirs()

        self.repo = DiffRepository(self.config.db.sqlite_path)
        self.pipeline = PipelineRunner(
            planner=JobPlanner(self.config),
            repo=self.repo,
            diff_engine=CsvDiffEngine(self.config.csv, self.config.diff),
            compare_tool_launcher=CompareToolLauncher(self.config.compare_tool),
            report_renderer=DetailedReportRenderer(self.config.report.output_dir),
            ai_client=AISummaryClient(self.config.ai),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_manual_compare_persists_and_generates_reports(self) -> None:
        job_id = self.pipeline.process_manual_pair(self.left, self.right)
        self.assertGreater(job_id, 0)
        self.assertIsNotNone(self.pipeline.last_batch_result)
        assert self.pipeline.last_batch_result is not None
        batch_slug = self.pipeline.last_batch_result.batch_slug

        job = self.repo.get_job(job_id)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job["status"], "done")
        self.assertIsNotNone(job.get("batch_id"))
        self.assertEqual(job.get("report_subdir_name"), "result")

        bundle = self.repo.fetch_job_bundle(job_id)
        self.assertIsNotNone(bundle["summary"])
        self.assertGreaterEqual(len(bundle["reports"]), 2)
        self.assertIsNotNone(bundle.get("batch"))
        self.assertGreaterEqual(len(bundle.get("batch_reports", [])), 2)

        report_root = Path(self.config.report.output_dir) / batch_slug
        report_dir = report_root / "result"
        self.assertTrue((report_dir / "detailed_report.html").exists())
        self.assertTrue((report_dir / "row_diffs.csv").exists())
        self.assertTrue((report_root / "index.html").exists())
        self.assertTrue((report_root / "summary.csv").exists())

        conn = sqlite3.connect(self.config.db.sqlite_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM diff_summaries WHERE job_id = ?", (job_id,)).fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], 1)

    def test_manual_compare_with_glob_runs_multiple_csv_jobs(self) -> None:
        (self.left / "DM.csv").write_text("id,val\n1,a\n", encoding="utf-8", newline="")
        (self.right / "DM.csv").write_text("id,val\n1,b\n", encoding="utf-8", newline="")
        (self.left / "CM.csv").write_text("id,val\n1,x\n", encoding="utf-8", newline="")
        (self.right / "CM.csv").write_text("id,val\n1,y\n", encoding="utf-8", newline="")

        self.config.csv.fixed_filename = "*.csv"
        job_ids = self.pipeline.process_manual_pairs(self.left, self.right)

        # Existing result.csv + CM.csv + DM.csv => 3 comparisons
        self.assertEqual(len(job_ids), 3)
        self.assertTrue(all(isinstance(i, int) and i > 0 for i in job_ids))
        self.assertIsNotNone(self.pipeline.last_batch_result)
        assert self.pipeline.last_batch_result is not None
        batch_slug = self.pipeline.last_batch_result.batch_slug
        batch_dir = Path(self.config.report.output_dir) / batch_slug
        self.assertTrue((batch_dir / "index.html").exists())
        self.assertTrue((batch_dir / "summary.csv").exists())
        self.assertTrue((batch_dir / "CM" / "detailed_report.html").exists())
        self.assertTrue((batch_dir / "DM" / "detailed_report.html").exists())
        self.assertTrue((batch_dir / "result" / "detailed_report.html").exists())

    def test_allocate_file_subdir_adds_suffix_on_collision(self) -> None:
        used: set[str] = set()
        first = self.pipeline._allocate_file_subdir(Path("DM.csv"), used)  # type: ignore[attr-defined]
        second = self.pipeline._allocate_file_subdir(Path("DM.csv"), used)  # type: ignore[attr-defined]
        third = self.pipeline._allocate_file_subdir(Path("dm.csv"), used)  # type: ignore[attr-defined]
        self.assertEqual(first, "DM")
        self.assertEqual(second, "DM__2")
        self.assertEqual(third, "dm__3")

    def test_batch_slug_format(self) -> None:
        slug = self.pipeline._build_batch_slug()  # type: ignore[attr-defined]
        self.assertRegex(slug, r"^results-\d{14}$")

    def test_repeated_same_pair_still_generates_file_reports(self) -> None:
        first_job_ids = self.pipeline.process_manual_pairs(self.left, self.right)
        self.assertTrue(first_job_ids)
        first_batch = self.pipeline.last_batch_result
        self.assertIsNotNone(first_batch)
        assert first_batch is not None

        second_job_ids = self.pipeline.process_manual_pairs(self.left, self.right)
        self.assertTrue(second_job_ids)
        second_batch = self.pipeline.last_batch_result
        self.assertIsNotNone(second_batch)
        assert second_batch is not None

        # Batches may collide if same second; force only path existence check on latest batch.
        latest_batch_dir = Path(self.config.report.output_dir) / second_batch.batch_slug / "result"
        self.assertTrue((latest_batch_dir / "detailed_report.html").exists())
        self.assertTrue((latest_batch_dir / "row_diffs.csv").exists())

        second_job = self.repo.get_job(second_job_ids[0])
        self.assertIsNotNone(second_job)
        assert second_job is not None
        self.assertEqual(second_job["status"], "done")

    def test_batch_ai_summary_is_generated_at_batch_root(self) -> None:
        self.config.ai = AIConfig(
            enabled=True,
            base_url="https://api.openai.com/v1",
            api_key="dummy",
            model="gpt-5-mini",
            timeout_sec=5,
            max_retries=0,
            send_raw_rows=False,
        )
        self.pipeline = PipelineRunner(
            planner=JobPlanner(self.config),
            repo=self.repo,
            diff_engine=CsvDiffEngine(self.config.csv, self.config.diff),
            compare_tool_launcher=CompareToolLauncher(self.config.compare_tool),
            report_renderer=DetailedReportRenderer(self.config.report.output_dir),
            ai_client=_StubBatchAISummaryClient(self.config.ai),
        )

        job_id = self.pipeline.process_manual_pair(self.left, self.right)
        self.assertGreater(job_id, 0)
        self.assertIsNotNone(self.pipeline.last_batch_result)
        assert self.pipeline.last_batch_result is not None
        batch_slug = self.pipeline.last_batch_result.batch_slug
        batch_root = Path(self.config.report.output_dir) / batch_slug

        self.assertTrue((batch_root / "batch_ai_summary.md").exists())
        content = (batch_root / "batch_ai_summary.md").read_text(encoding="utf-8")
        self.assertIn("Batch AI Summary", content)

        bundle = self.repo.fetch_job_bundle(job_id)
        batch_reports = bundle.get("batch_reports", [])
        self.assertTrue(any(r.get("report_type") == "batch_ai_summary_md" for r in batch_reports))


if __name__ == "__main__":
    unittest.main()
