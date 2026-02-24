from __future__ import annotations

import unittest

from medaudit_diff_watcher.ai_client import AISummaryClient
from medaudit_diff_watcher.config import AIConfig
from medaudit_diff_watcher.models import (
    CsvDiffResult,
    CsvDiffSummary,
    FileSnapshot,
    SchemaDiff,
)


class _NoNetworkAISummaryClient(AISummaryClient):
    def _post_json(self, *args, **kwargs):  # type: ignore[override]
        raise AssertionError("Network call should not happen for identical CSV template path")


class AISummaryClientTemplateTests(unittest.TestCase):
    def test_identical_csv_uses_fixed_template(self) -> None:
        client = _NoNetworkAISummaryClient(
            AIConfig(
                enabled=True,
                base_url="https://api.openai.com/v1",
                api_key="dummy",
                model="gpt-5-mini",
                timeout_sec=5,
                max_retries=0,
                send_raw_rows=False,
            )
        )

        result = CsvDiffResult(
            left_snapshot=FileSnapshot(path="left.csv", file_size=10, mtime=1.0, sha256="a"),
            right_snapshot=FileSnapshot(path="right.csv", file_size=10, mtime=1.0, sha256="b"),
            schema_diff=SchemaDiff(
                left_headers=["A", "B"],
                right_headers=["A", "B"],
                added_columns=[],
                removed_columns=[],
                reordered_columns=[],
            ),
            summary=CsvDiffSummary(
                total_rows_left=2,
                total_rows_right=2,
                exact_match_rows=2,
                added_rows=0,
                deleted_rows=0,
                suspected_modified_rows=0,
                fuzzy_match_enabled=True,
            ),
            added_rows=[],
            deleted_rows=[],
            suspected_modified_rows=[],
            warnings=[],
        )

        summary = client.generate_summary(result)

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.model, "local-template-identical")
        self.assertIn("固定模板", summary.summary_text)
        self.assertIn("无差异", summary.summary_text)
        self.assertIn("未发现字段值变化", summary.summary_text)

    def test_identical_batch_uses_fixed_template(self) -> None:
        client = _NoNetworkAISummaryClient(
            AIConfig(
                enabled=True,
                base_url="https://api.openai.com/v1",
                api_key="dummy",
                model="gpt-5-mini",
                timeout_sec=5,
                max_retries=0,
                send_raw_rows=False,
            )
        )

        summary = client.generate_batch_summary(
            batch_meta={"batch_slug": "results-20260224140000"},
            file_rows=[
                {
                    "file_name": "DM.csv",
                    "status": "done",
                    "total_rows_left": 200,
                    "total_rows_right": 200,
                    "exact_match_rows": 200,
                    "added_rows": 0,
                    "deleted_rows": 0,
                    "suspected_modified_rows": 0,
                    "added_columns_count": 0,
                    "removed_columns_count": 0,
                    "reordered_columns_count": 0,
                },
                {
                    "file_name": "CM.csv",
                    "status": "done",
                    "total_rows_left": 20,
                    "total_rows_right": 20,
                    "exact_match_rows": 20,
                    "added_rows": 0,
                    "deleted_rows": 0,
                    "suspected_modified_rows": 0,
                    "added_columns_count": 0,
                    "removed_columns_count": 0,
                    "reordered_columns_count": 0,
                },
            ],
        )

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertEqual(summary.model, "local-template-batch-identical")
        self.assertIn("批次AI总结（固定模板）", summary.summary_text)
        self.assertIn("2 个文件", summary.summary_text)
        self.assertIn("均为无差异", summary.summary_text)


if __name__ == "__main__":
    unittest.main()
