from __future__ import annotations

import unittest
from pathlib import Path

from medaudit_diff_watcher.compare_tool_launcher import CompareToolLauncher
from medaudit_diff_watcher.config import CompareToolConfig


class CompareToolLauncherTests(unittest.TestCase):
    def test_auto_detects_winmerge_from_exe_name(self) -> None:
        launcher = CompareToolLauncher(
            CompareToolConfig(
                enabled=True,
                executable_path=r"C:\Program Files\WinMerge\WinMergeU.exe",
                compare_mode="folder",
            )
        )
        self.assertEqual(launcher.tool_kind(), "winmerge")
        self.assertEqual(launcher.tool_display_name(), "WinMerge")

    def test_missing_winmerge_path_uses_winmerge_error_name(self) -> None:
        launcher = CompareToolLauncher(
            CompareToolConfig(
                enabled=True,
                executable_path=r"C:\Program Files\WinMerge\WinMergeU.exe.__missing__",
                compare_mode="folder",
            )
        )
        result = launcher.launch(
            left_folder=Path("C:/left"),
            right_folder=Path("C:/right"),
            left_csv=Path("C:/left/a.csv"),
            right_csv=Path("C:/right/a.csv"),
        )
        self.assertFalse(result.launched)
        self.assertIn("WinMerge executable not found", result.error or "")

    def test_build_command_for_winmerge_folder_mode(self) -> None:
        launcher = CompareToolLauncher(
            CompareToolConfig(
                enabled=True,
                executable_path=r"C:\Program Files\WinMerge\WinMergeU.exe",
                compare_mode="folder",
                tool="winmerge",
            )
        )
        cmd = launcher._build_command(  # type: ignore[attr-defined]
            exe=Path(r"C:\Program Files\WinMerge\WinMergeU.exe"),
            tool_kind="winmerge",
            mode="folder",
            left_folder=Path(r"C:\A"),
            right_folder=Path(r"C:\B"),
            left_csv=Path(r"C:\A\DM.csv"),
            right_csv=Path(r"C:\B\DM.csv"),
        )
        self.assertEqual(cmd, [r"C:\Program Files\WinMerge\WinMergeU.exe", r"C:\A", r"C:\B"])


if __name__ == "__main__":
    unittest.main()
