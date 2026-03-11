from __future__ import annotations

from pathlib import Path
import fnmatch

from medaudit_diff_watcher.config import AppConfig
from medaudit_diff_watcher.models import PlannedComparison


class JobPlanner:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def list_subfolders(self) -> list[Path]:
        root = Path(self.config.watch.root_dir).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"Watch root does not exist: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Watch root is not a directory: {root}")
        return [p for p in root.iterdir() if p.is_dir()]

    def _sort_key(self, folder: Path) -> tuple[float, str]:
        stat = folder.stat()
        return (stat.st_mtime, folder.name.lower())

    def select_latest_two(self, folders: list[Path]) -> tuple[Path, Path] | None:
        if self.config.pairing.strategy != "latest_two":
            raise ValueError(f"Unsupported pairing strategy: {self.config.pairing.strategy}")
        if len(folders) < self.config.watch.min_subfolders_to_compare:
            return None
        ordered = sorted(folders, key=self._sort_key)
        return ordered[-2], ordered[-1]

    def build_plan_for_pair(self, left_folder: Path, right_folder: Path) -> PlannedComparison:
        filename = self.config.csv.fixed_filename
        left_csv = left_folder / filename
        right_csv = right_folder / filename
        return PlannedComparison(
            left_folder=left_folder,
            right_folder=right_folder,
            left_csv=left_csv,
            right_csv=right_csv,
            sort_key_left=self._sort_key(left_folder),
            sort_key_right=self._sort_key(right_folder),
        )

    def build_plans_for_pair(self, left_folder: Path, right_folder: Path) -> list[PlannedComparison]:
        pattern = self.config.csv.fixed_filename.strip()
        if self._is_glob_pattern(pattern):
            return self._build_glob_plans_for_pair(left_folder, right_folder, pattern)
        return [self.build_plan_for_pair(left_folder, right_folder)]

    def _is_glob_pattern(self, pattern: str) -> bool:
        return any(ch in pattern for ch in "*?[]")

    def _list_csv_files(self, folder: Path) -> list[Path]:
        return sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".csv"], key=lambda p: p.name.lower())

    def _build_glob_plans_for_pair(self, left_folder: Path, right_folder: Path, pattern: str) -> list[PlannedComparison]:
        left_files = self._list_csv_files(left_folder)
        right_files = self._list_csv_files(right_folder)
        left_map = {p.name.lower(): p for p in left_files if fnmatch.fnmatch(p.name, pattern)}
        right_map = {p.name.lower(): p for p in right_files if fnmatch.fnmatch(p.name, pattern)}
        all_keys = sorted(set(left_map.keys()) | set(right_map.keys()))
        plans: list[PlannedComparison] = []
        for key in all_keys:
            left_csv = left_map.get(key)
            right_csv = right_map.get(key)
            display_name = (left_csv or right_csv).name
            plans.append(
                PlannedComparison(
                    left_folder=left_folder,
                    right_folder=right_folder,
                    left_csv=left_csv or (left_folder / display_name),
                    right_csv=right_csv or (right_folder / display_name),
                    sort_key_left=self._sort_key(left_folder),
                    sort_key_right=self._sort_key(right_folder),
                )
            )
        return plans

    def plan_latest_pair(self) -> PlannedComparison | None:
        folders = self.list_subfolders()
        pair = self.select_latest_two(folders)
        if pair is None:
            return None
        return self.build_plan_for_pair(pair[0], pair[1])

    def plan_latest_pairs(self) -> list[PlannedComparison]:
        folders = self.list_subfolders()
        pair = self.select_latest_two(folders)
        if pair is None:
            return []
        return self.build_plans_for_pair(pair[0], pair[1])

    def describe_csv_files(self, folder: Path) -> list[str]:
        try:
            return [p.name for p in self._list_csv_files(folder)]
        except Exception:
            return []
