from __future__ import annotations

import subprocess
from pathlib import Path

from medaudit_diff_watcher.config import CompareToolConfig
from medaudit_diff_watcher.models import LaunchResult


class CompareToolLauncher:
    def __init__(self, config: CompareToolConfig) -> None:
        self.config = config

    def tool_kind(self) -> str:
        return self._resolve_tool_kind(Path(self.config.executable_path).expanduser())

    def tool_display_name(self) -> str:
        kind = self.tool_kind()
        if kind == "winmerge":
            return "WinMerge"
        if kind == "bcompare":
            return "Beyond Compare"
        return "Diff tool"

    def launch(
        self,
        *,
        left_folder: Path,
        right_folder: Path,
        left_csv: Path,
        right_csv: Path,
    ) -> LaunchResult:
        if not self.config.enabled:
            return LaunchResult(launched=False, command=[], error=None)

        exe = Path(self.config.executable_path).expanduser()
        if not exe.exists():
            return LaunchResult(
                launched=False,
                command=[str(exe)],
                error=f"{self.tool_display_name()} executable not found: {exe}",
            )

        mode = self.config.compare_mode.lower().strip()
        tool_kind = self._resolve_tool_kind(exe)
        cmd = self._build_command(
            exe=exe,
            tool_kind=tool_kind,
            mode=mode,
            left_folder=left_folder,
            right_folder=right_folder,
            left_csv=left_csv,
            right_csv=right_csv,
        )

        try:
            subprocess.Popen(cmd)  # noqa: S603 - user-configured executable on local machine
            return LaunchResult(launched=True, command=cmd)
        except Exception as exc:  # pragma: no cover - platform/process dependent
            return LaunchResult(launched=False, command=cmd, error=str(exc))

    def _build_command(
        self,
        *,
        exe: Path,
        tool_kind: str,
        mode: str,
        left_folder: Path,
        right_folder: Path,
        left_csv: Path,
        right_csv: Path,
    ) -> list[str]:
        # WinMerge and Beyond Compare both accept `exe left right` for file/folder opening.
        if mode == "folder":
            left = left_folder
            right = right_folder
        else:
            left = left_csv
            right = right_csv

        cmd = [str(exe), str(left), str(right)]
        if tool_kind == "winmerge":
            # `/u` is implied for WinMergeU.exe; no extra switches to preserve manual UI behavior.
            return cmd
        return cmd

    def _resolve_tool_kind(self, exe: Path) -> str:
        explicit = (self.config.tool or "auto").strip().lower()
        if explicit in {"bcompare", "beyond_compare", "beyondcompare"}:
            return "bcompare"
        if explicit in {"winmerge", "winmergeu"}:
            return "winmerge"
        name = exe.name.lower()
        if "winmerge" in name:
            return "winmerge"
        if "bcompare" in name or name.startswith("bcomp"):
            return "bcompare"
        return "generic"
