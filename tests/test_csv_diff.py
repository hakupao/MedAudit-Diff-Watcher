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


if __name__ == "__main__":
    unittest.main()

