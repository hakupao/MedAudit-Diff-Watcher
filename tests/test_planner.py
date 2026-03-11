from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

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
from medaudit_diff_watcher.planner import JobPlanner


class PlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = AppConfig(
            watch=WatchConfig(root_dir=str(self.root), scan_interval_sec=1, stable_wait_sec=1),
            pairing=PairingConfig(strategy="latest_two"),
            csv=CsvConfig(fixed_filename="result.csv"),
            diff=DiffConfig(),
            compare_tool=CompareToolConfig(enabled=False),
            db=DBConfig(sqlite_path=str(self.root / "data.sqlite")),
            report=ReportConfig(output_dir=str(self.root / "reports")),
            ai=AIConfig(enabled=False),
            logging=LoggingConfig(level="INFO"),
        )
        self.planner = JobPlanner(self.config)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_select_latest_two(self) -> None:
        a = self.root / "a"
        b = self.root / "b"
        c = self.root / "c"
        for p in (a, b, c):
            p.mkdir()
            (p / "result.csv").write_text("x\n1\n", encoding="utf-8")
            time.sleep(0.05)
        pair = self.planner.select_latest_two([a, b, c])
        self.assertIsNotNone(pair)
        assert pair is not None
        self.assertEqual(pair[0].name, "b")
        self.assertEqual(pair[1].name, "c")

    def test_plan_latest_pair_includes_fixed_filename(self) -> None:
        for name in ("a", "b"):
            d = self.root / name
            d.mkdir()
            (d / "result.csv").write_text("x\n1\n", encoding="utf-8")
            time.sleep(0.02)
        plan = self.planner.plan_latest_pair()
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertTrue(plan.left_csv.name == "result.csv")
        self.assertTrue(plan.right_csv.name == "result.csv")

    def test_plan_latest_pairs_supports_glob(self) -> None:
        self.config.csv.fixed_filename = "*.csv"
        a = self.root / "a"
        b = self.root / "b"
        a.mkdir()
        b.mkdir()
        for name in ("CM.csv", "DM.csv", "ignore.txt"):
            (a / name).write_text("id\n1\n", encoding="utf-8")
        for name in ("CM.csv", "DM.csv", "RS.csv"):
            (b / name).write_text("id\n1\n", encoding="utf-8")
        time.sleep(0.05)
        plans = self.planner.plan_latest_pairs()
        self.assertEqual([p.left_csv.name for p in plans], ["CM.csv", "DM.csv", "RS.csv"])
        self.assertFalse(plans[-1].left_csv.exists())
        self.assertTrue(plans[-1].right_csv.exists())


if __name__ == "__main__":
    unittest.main()
