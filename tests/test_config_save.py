from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from medaudit_diff_watcher.config import (
    AIConfig,
    AppConfig,
    CompareToolConfig,
    CsvConfig,
    DEFAULT_EXCLUDE_COLUMNS_REGEX,
    DBConfig,
    DiffConfig,
    LoggingConfig,
    PairingConfig,
    ReportConfig,
    WatchConfig,
    load_config,
    save_config,
)


class ConfigSaveTests(unittest.TestCase):
    def test_save_and_load_roundtrip_preserves_core_values(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            cfg_path = base / "config.gui-dev.yaml"
            cfg = AppConfig(
                watch=WatchConfig(
                    root_dir=str(base / "watch"),
                    root_dirs=[],
                    scan_interval_sec=12,
                    stable_wait_sec=3,
                    min_subfolders_to_compare=2,
                ),
                pairing=PairingConfig(strategy="latest_two"),
                csv=CsvConfig(fixed_filename="*.csv", exclude_columns_regex=["^USUBJID$", "^[A-Za-z]{2}SEQ$"]),
                diff=DiffConfig(enable_fuzzy_match=False, fuzzy_threshold=95, max_fuzzy_comparisons=1234),
                compare_tool=CompareToolConfig(enabled=False, executable_path="", compare_mode="folder", tool="auto"),
                db=DBConfig(sqlite_path=str(base / "data_gui_dev" / "medaudit.db")),
                report=ReportConfig(output_dir=str(base / "reports_gui_dev")),
                ai=AIConfig(enabled=False),
                logging=LoggingConfig(level="INFO"),
            )

            save_config(cfg_path, cfg)
            loaded = load_config(cfg_path)

            self.assertEqual(loaded.watch.root_dir, cfg.watch.root_dir)
            self.assertEqual(loaded.csv.fixed_filename, "*.csv")
            self.assertEqual(loaded.csv.exclude_columns_regex, ["^USUBJID$", "^[A-Za-z]{2}SEQ$"])
            self.assertEqual(loaded.diff.enable_fuzzy_match, False)
            self.assertEqual(Path(loaded.db.sqlite_path), Path(cfg.db.sqlite_path))
            self.assertEqual(Path(loaded.report.output_dir), Path(cfg.report.output_dir))

    def test_load_config_without_exclude_columns_regex_uses_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "config.yaml"
            cfg_path.write_text(
                "\n".join(
                    [
                        "watch:",
                        '  root_dir: "C:\\\\Study\\\\04_SDTM"',
                        "pairing:",
                        "  strategy: latest_two",
                        "csv:",
                        '  fixed_filename: "*.csv"',
                        "diff:",
                        "  enable_fuzzy_match: true",
                    ]
                ),
                encoding="utf-8",
            )

            loaded = load_config(cfg_path)

            self.assertEqual(loaded.csv.exclude_columns_regex, DEFAULT_EXCLUDE_COLUMNS_REGEX)


if __name__ == "__main__":
    unittest.main()
