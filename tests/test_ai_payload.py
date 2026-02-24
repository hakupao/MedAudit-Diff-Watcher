from __future__ import annotations

import unittest

from medaudit_diff_watcher.models import (
    CellDiff,
    CsvDiffResult,
    CsvDiffSummary,
    FileSnapshot,
    SchemaDiff,
    SuspectedModifiedRow,
)


class AIPayloadTests(unittest.TestCase):
    def _make_result(self) -> CsvDiffResult:
        snapshot_left = FileSnapshot(path="left.csv", file_size=1, mtime=1.0, sha256="a")
        snapshot_right = FileSnapshot(path="right.csv", file_size=1, mtime=2.0, sha256="b")
        schema = SchemaDiff(
            left_headers=["USUBJID", "AGEU"],
            right_headers=["USUBJID", "AGEU"],
            added_columns=[],
            removed_columns=[],
            reordered_columns=[],
        )
        summary = CsvDiffSummary(
            total_rows_left=2,
            total_rows_right=2,
            exact_match_rows=0,
            added_rows=0,
            deleted_rows=0,
            suspected_modified_rows=2,
            fuzzy_match_enabled=True,
        )
        rows = [
            SuspectedModifiedRow(
                match_group_id="g1",
                left_row={"USUBJID": "01", "AGEU": "YEARS"},
                right_row={"USUBJID": "01", "AGEU": "YEAR"},
                confidence=100.0,
                cell_diffs=[CellDiff(column_name="AGEU", left_value="YEARS", right_value="YEAR")],
            ),
            SuspectedModifiedRow(
                match_group_id="g2",
                left_row={"USUBJID": "02", "AGEU": "YEARS"},
                right_row={"USUBJID": "02", "AGEU": "YEAR"},
                confidence=88.5,
                cell_diffs=[CellDiff(column_name="AGEU", left_value="YEARS", right_value="YEAR")],
            ),
        ]
        return CsvDiffResult(
            left_snapshot=snapshot_left,
            right_snapshot=snapshot_right,
            schema_diff=schema,
            summary=summary,
            added_rows=[],
            deleted_rows=[],
            suspected_modified_rows=rows,
        )

    def test_ai_payload_includes_field_change_patterns_and_omits_confidence_by_default(self) -> None:
        payload = self._make_result().to_ai_payload(include_raw_rows=False)

        self.assertIn("field_change_patterns", payload)
        patterns = payload["field_change_patterns"]["columns"]
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["column_name"], "AGEU")
        self.assertEqual(patterns[0]["changed_row_count"], 2)
        self.assertEqual(patterns[0]["top_value_transitions"][0]["left_value"], "YEARS")
        self.assertEqual(patterns[0]["top_value_transitions"][0]["right_value"], "YEAR")
        self.assertEqual(patterns[0]["top_value_transitions"][0]["count"], 2)

        sample_row = payload["samples"]["suspected_modified_rows"][0]
        self.assertNotIn("confidence", sample_row)


if __name__ == "__main__":
    unittest.main()
