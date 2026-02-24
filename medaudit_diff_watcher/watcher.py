from __future__ import annotations

import queue
import threading
import time
from pathlib import Path
from typing import Callable

from medaudit_diff_watcher.planner import JobPlanner
from medaudit_diff_watcher.stability import FolderStabilityChecker


class WatcherService:
    def __init__(
        self,
        *,
        planner: JobPlanner,
        stability_checker: FolderStabilityChecker,
        on_trigger: Callable[[str], None],
        scan_interval_sec: int,
    ) -> None:
        self.planner = planner
        self.stability_checker = stability_checker
        self.on_trigger = on_trigger
        self.scan_interval_sec = max(1, scan_interval_sec)
        self._stop_event = threading.Event()
        self._candidates: "queue.Queue[Path]" = queue.Queue()
        self._known_folders: set[str] = set()
        self._observer = None

    def run(self) -> None:
        root = Path(self.planner.config.watch.root_dir).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self._known_folders = {str(p.resolve()) for p in self.planner.list_subfolders()}
        self._setup_watchdog_if_available(root)

        # Startup scan can immediately process existing latest pair.
        self.on_trigger("startup_scan")

        try:
            while not self._stop_event.is_set():
                self._poll_for_new_folders()
                self._drain_candidates()
                time.sleep(self.scan_interval_sec)
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        if self._observer is not None:  # pragma: no cover - optional dependency path
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

    def _setup_watchdog_if_available(self, root: Path) -> None:
        try:
            from watchdog.events import FileSystemEventHandler  # type: ignore
            from watchdog.observers import Observer  # type: ignore
        except Exception:
            return

        svc = self

        class _Handler(FileSystemEventHandler):
            def on_created(self, event):  # type: ignore[no-untyped-def]
                if getattr(event, "is_directory", False):
                    svc._candidates.put(Path(event.src_path))

            def on_moved(self, event):  # type: ignore[no-untyped-def]
                dest = getattr(event, "dest_path", None)
                if dest:
                    svc._candidates.put(Path(dest))

        observer = Observer()
        observer.schedule(_Handler(), str(root), recursive=False)
        observer.start()
        self._observer = observer

    def _poll_for_new_folders(self) -> None:
        try:
            folders = self.planner.list_subfolders()
        except Exception:
            return
        for folder in folders:
            key = str(folder.resolve())
            if key not in self._known_folders:
                self._known_folders.add(key)
                self._candidates.put(folder)

    def _drain_candidates(self) -> None:
        processed_any = False
        while True:
            try:
                candidate = self._candidates.get_nowait()
            except queue.Empty:
                break
            if not candidate.exists() or not candidate.is_dir():
                continue
            if not self.stability_checker.wait_until_stable(candidate):
                continue
            processed_any = True
        if processed_any:
            self.on_trigger("folder_stable")

