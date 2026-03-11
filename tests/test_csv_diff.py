from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from medaudit_diff_watcher.config import CsvConfig, DiffConfig
from medaudit_diff_watcher.csv_diff import CsvDiffEngine


class CsvDiffEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = CsvDiffEngine(
            CsvConfig(fixed_filename="result.csv"),
            DiffConfig(enable_fuzzy_match=True, fuzzy_threshold=80, max_fuzzy_comparisons=1000),
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8", newline="")

    def test_row_order_change_counts_as_exact(self) -> None:
        left = self.root / "left.csv"
        right = self.root / "right.csv"
        self._write(left, "id,name\n1,A\n2,B\n")
        self._write(right, "id,name\n2,B\n1,A\n")

        result = self.engine.compare_files(left, right)

        self.assertEqual(result.summary.exact_match_rows, 2)
        self.assertEqual(result.summary.added_rows, 0)
        self.assertEqual(result.summary.deleted_rows, 0)
        self.assertEqual(result.summary.suspected_modified_rows, 0)

    def test_modified_row_can_be_detected_as_suspected(self) -> None:
        left = self.root / "left.csv"
        right = self.root / "right.csv"
        self._write(left, "id,name,score\n1,Alice,10\n2,Bob,20\n")
        self._write(right, "id,name,score\n1,Alice,10\n2,Bob,25\n")

        result = self.engine.compare_files(left, right)

        self.assertEqual(result.summary.exact_match_rows, 1)
        self.assertEqual(result.summary.suspected_modified_rows, 1)
        self.assertEqual(result.summary.added_rows, 0)
        self.assertEqual(result.summary.deleted_rows, 0)
        changed_columns = [c.column_name for c in result.suspected_modified_rows[0].cell_diffs]
        self.assertIn("score", changed_columns)

    def test_default_xxseq_columns_are_excluded_from_comparison(self) -> None:
        left = self.root / "left.csv"
        right = self.root / "right.csv"
        self._write(left, "id,DMSEQ,name\n1,100,Alice\n")
        self._write(right, "id,DMSEQ,name\n1,999,Alice\n")

        result = self.engine.compare_files(left, right)

        self.assertEqual(result.schema_diff.left_headers, ["id", "name"])
        self.assertEqual(result.schema_diff.right_headers, ["id", "name"])
        self.assertEqual(result.summary.exact_match_rows, 1)
        self.assertEqual(result.summary.added_rows, 0)
        self.assertEqual(result.summary.deleted_rows, 0)
        self.assertEqual(result.summary.suspected_modified_rows, 0)

    def test_custom_exclude_regex_can_hide_schema_and_row_diffs(self) -> None:
        engine = CsvDiffEngine(
            CsvConfig(fixed_filename="result.csv", exclude_columns_regex=[r"TEMP_.*"]),
            DiffConfig(enable_fuzzy_match=True, fuzzy_threshold=80, max_fuzzy_comparisons=1000),
        )
        left = self.root / "left-custom.csv"
        right = self.root / "right-custom.csv"
        self._write(left, "id,name,TEMP_NOTE\n1,Alice,left-only\n")
        self._write(right, "id,name\n1,Alice\n")

        result = engine.compare_files(left, right)

        self.assertEqual(result.schema_diff.added_columns, [])
        self.assertEqual(result.schema_diff.removed_columns, [])
        self.assertEqual(result.summary.exact_match_rows, 1)
        self.assertEqual(result.summary.added_rows, 0)
        self.assertEqual(result.summary.deleted_rows, 0)

    def test_missing_right_file_is_treated_as_full_deletion(self) -> None:
        left = self.root / "left-only.csv"
        right = self.root / "missing-right.csv"
        self._write(left, "id,name\n1,Alice\n2,Bob\n")

        result = self.engine.compare_files(left, right)

        self.assertEqual(result.summary.total_rows_left, 2)
        self.assertEqual(result.summary.total_rows_right, 0)
        self.assertEqual(result.summary.added_rows, 0)
        self.assertEqual(result.summary.deleted_rows, 2)
        self.assertEqual(result.schema_diff.removed_columns, ["id", "name"])
        self.assertTrue(any("missing right file as empty" in warning.lower() for warning in result.warnings))

    def test_missing_left_file_is_treated_as_full_addition(self) -> None:
        left = self.root / "missing-left.csv"
        right = self.root / "right-only.csv"
        self._write(right, "id,name\n1,Alice\n")

        result = self.engine.compare_files(left, right)

        self.assertEqual(result.summary.total_rows_left, 0)
        self.assertEqual(result.summary.total_rows_right, 1)
        self.assertEqual(result.summary.added_rows, 1)
        self.assertEqual(result.summary.deleted_rows, 0)
        self.assertEqual(result.schema_diff.added_columns, ["id", "name"])


if __name__ == "__main__":
    unittest.main()
