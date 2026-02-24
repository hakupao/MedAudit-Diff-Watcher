from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class FolderSignature:
    file_count: int
    total_size: int
    newest_mtime: float


class FolderStabilityChecker:
    def __init__(self, stable_wait_sec: int, poll_interval_sec: float = 1.0) -> None:
        self.stable_wait_sec = max(1, stable_wait_sec)
        self.poll_interval_sec = max(0.2, poll_interval_sec)

    def snapshot(self, folder: Path) -> FolderSignature:
        file_count = 0
        total_size = 0
        newest_mtime = 0.0
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            file_count += 1
            total_size += stat.st_size
            newest_mtime = max(newest_mtime, stat.st_mtime)
        return FolderSignature(file_count=file_count, total_size=total_size, newest_mtime=newest_mtime)

    def wait_until_stable(self, folder: Path, *, max_wait_sec: int = 600) -> bool:
        deadline = time.time() + max_wait_sec
        while time.time() < deadline:
            first = self.snapshot(folder)
            time.sleep(self.stable_wait_sec)
            if not folder.exists():
                return False
            second = self.snapshot(folder)
            if first == second:
                return True
            time.sleep(self.poll_interval_sec)
        return False

