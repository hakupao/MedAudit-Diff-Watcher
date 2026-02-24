from __future__ import annotations

import tempfile
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
    expand_watch_scopes,
)


class MultiWatchConfigTests(unittest.TestCase):
    def _base_app_config(self, root_dir: str = "", root_dirs: list[str] | None = None, *, base: Path) -> AppConfig:
        return AppConfig(
            watch=WatchConfig(
                root_dir=root_dir,
                root_dirs=root_dirs or [],
                scan_interval_sec=1,
                stable_wait_sec=1,
                min_subfolders_to_compare=2,
            ),
            pairing=PairingConfig(strategy="latest_two"),
            csv=CsvConfig(fixed_filename="result.csv"),
            diff=DiffConfig(),
            compare_tool=CompareToolConfig(enabled=False, executable_path=""),
            db=DBConfig(sqlite_path=str(base / "data" / "medaudit.db")),
            report=ReportConfig(output_dir=str(base / "reports")),
            ai=AIConfig(enabled=False),
            logging=LoggingConfig(level="INFO"),
        )

    def test_single_legacy_root_dir_keeps_non_namespaced_storage(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            watch_root = base / "watchA"
            watch_root.mkdir()
            cfg = self._base_app_config(root_dir=str(watch_root), base=base)
            scopes = expand_watch_scopes(cfg)

            self.assertEqual(len(scopes), 1)
            self.assertEqual(scopes[0].name, "default")
            self.assertEqual(Path(scopes[0].config.db.sqlite_path), base / "data" / "medaudit.db")
            self.assertEqual(Path(scopes[0].config.report.output_dir), base / "reports")

    def test_root_dirs_use_isolated_db_and_report_per_watch_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            root1 = base / "projA" / "04_SDTM"
            root2 = base / "projB" / "04_SDTM"
            root3 = base / "projC" / "adam"
            root1.mkdir(parents=True)
            root2.mkdir(parents=True)
            root3.mkdir(parents=True)
            cfg = self._base_app_config(root_dirs=[str(root1), str(root2), str(root3)], base=base)

            scopes = expand_watch_scopes(cfg)

            self.assertEqual(len(scopes), 3)
            names = [s.name for s in scopes]
            self.assertEqual(names[0], "04_SDTM")
            self.assertEqual(names[1], "04_SDTM__2")
            self.assertEqual(names[2], "adam")

            for scope in scopes:
                db_path = Path(scope.config.db.sqlite_path)
                report_dir = Path(scope.config.report.output_dir)
                self.assertEqual(db_path.name, "medaudit.db")
                self.assertEqual(db_path.parent.name, scope.name)
                self.assertEqual(report_dir.name, scope.name)
                self.assertTrue(report_dir.exists())
                self.assertTrue(db_path.parent.exists())


if __name__ == "__main__":
    unittest.main()
