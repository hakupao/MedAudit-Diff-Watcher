from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


DEFAULT_GUI_DEV_CONFIG_NAME = "config.gui-dev.yaml"
DEFAULT_GUI_DEV_DB_PATH = "data_gui_dev/medaudit_diff_gui.db"
DEFAULT_GUI_DEV_REPORT_DIR = "reports_gui_dev"


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    output: str
    started_at: float
    finished_at: float


def open_path_external(path: str | Path) -> None:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Path not found: {p}")
    if os.name == "nt":
        os.startfile(str(p))  # type: ignore[attr-defined]
        return
    webbrowser.open(p.as_uri())


def clone_config_file(src: str | Path, dst: str | Path, *, overwrite: bool = False) -> Path:
    src_path = Path(src).expanduser()
    dst_path = Path(dst).expanduser()
    if not src_path.exists():
        raise FileNotFoundError(f"Source config not found: {src_path}")
    if dst_path.exists() and not overwrite:
        raise FileExistsError(f"Target config already exists: {dst_path}")
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src_path, dst_path)
    return dst_path


def default_gui_dev_base_dir() -> Path:
    if getattr(sys, "frozen", False) and os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local_app_data) / "MedAuditDiffWatcher"
    return Path.cwd()


def default_gui_dev_config_path() -> Path:
    return default_gui_dev_base_dir() / DEFAULT_GUI_DEV_CONFIG_NAME


def ensure_gui_dev_config_file(target_path: str | Path = DEFAULT_GUI_DEV_CONFIG_NAME) -> Path:
    target = Path(target_path).expanduser()
    if target.exists():
        return target

    templates = [Path("config.gui-dev.example.yaml"), Path("config.example.yaml")]
    template = next((p for p in templates if p.exists()), None)
    if template is not None:
        try:
            import yaml  # type: ignore

            with template.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
            if isinstance(raw, dict):
                raw.setdefault("db", {})
                raw.setdefault("report", {})
                raw.setdefault("watch", {})
                base_dir = target.parent if target.parent != Path("") else default_gui_dev_base_dir()
                use_absolute_runtime_paths = target.is_absolute() or getattr(sys, "frozen", False)
                raw["db"]["sqlite_path"] = (
                    str((base_dir / "data" / "medaudit_diff_gui.db").resolve())
                    if use_absolute_runtime_paths
                    else DEFAULT_GUI_DEV_DB_PATH
                )
                raw["report"]["output_dir"] = (
                    str((base_dir / "reports").resolve()) if use_absolute_runtime_paths else DEFAULT_GUI_DEV_REPORT_DIR
                )
                raw["watch"].setdefault("root_dir", "C:\\Path\\To\\GUI-TEST\\04_SDTM")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("w", encoding="utf-8") as fh:
                    yaml.safe_dump(raw, fh, sort_keys=False, allow_unicode=True)
                return target
        except Exception:
            # Fall back to a minimal template below if PyYAML isn't available.
            pass

    target.parent.mkdir(parents=True, exist_ok=True)
    base_dir = target.parent if target.parent != Path("") else default_gui_dev_base_dir()
    use_absolute_runtime_paths = target.is_absolute() or getattr(sys, "frozen", False)
    db_path = str((base_dir / "data" / "medaudit_diff_gui.db").resolve()) if use_absolute_runtime_paths else DEFAULT_GUI_DEV_DB_PATH
    report_dir = str((base_dir / "reports").resolve()) if use_absolute_runtime_paths else DEFAULT_GUI_DEV_REPORT_DIR
    target.write_text(
        (
            "watch:\n"
            "  root_dir: \"C:\\\\Path\\\\To\\\\GUI-TEST\\\\04_SDTM\"\n"
            "  scan_interval_sec: 30\n"
            "  stable_wait_sec: 5\n"
            "  min_subfolders_to_compare: 2\n"
            "pairing:\n"
            "  strategy: latest_two\n"
            "csv:\n"
            "  fixed_filename: \"*.csv\"\n"
            "  encoding: auto\n"
            "  delimiter: auto\n"
            "diff:\n"
            "  enable_fuzzy_match: true\n"
            "compare_tool:\n"
            "  enabled: false\n"
            "  executable_path: \"\"\n"
            "db:\n"
            f"  sqlite_path: \"{db_path}\"\n"
            "report:\n"
            f"  output_dir: \"{report_dir}\"\n"
            "ai:\n"
            "  enabled: false\n"
            "logging:\n"
            "  level: INFO\n"
        ),
        encoding="utf-8",
    )
    return target


def resolve_cli_command_base() -> list[str]:
    # Source/dev mode: use current interpreter + module invocation.
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", "medaudit_diff_watcher"]

    # Packaged mode: prefer sibling CLI executable if bundled.
    exe_dir = Path(sys.executable).resolve().parent
    sibling_candidates = [
        exe_dir / "medaudit-diff-watcher.exe",
        exe_dir / "medaudit_diff_watcher_cli.exe",
    ]
    for candidate in sibling_candidates:
        if candidate.exists():
            return [str(candidate)]

    # Fallback to the frozen executable if it doubles as the CLI.
    return [sys.executable]


class CliSubprocessController:
    def __init__(self, *, config_path: str | Path, cwd: str | Path | None = None) -> None:
        self.config_path = str(Path(config_path).expanduser())
        self.cwd = str(Path(cwd).expanduser().resolve()) if cwd else str(Path.cwd())
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._log_lines: deque[str] = deque(maxlen=300)
        self._pump_thread: threading.Thread | None = None
        self._last_start_ts: float | None = None
        self._last_exit_code: int | None = None
        self._last_command: list[str] = []
        self._lockfile = Path(self.config_path).with_suffix(Path(self.config_path).suffix + ".guiwatch.lock")

    def build_command(self, subcommand: str, *extra_args: str) -> list[str]:
        cmd = resolve_cli_command_base()
        cmd.extend(["--config", self.config_path, subcommand])
        cmd.extend(extra_args)
        return cmd

    def start_watcher(self) -> None:
        with self._lock:
            if self._process and self._process.poll() is None:
                return
            self._warn_if_stale_lock()
            cmd = self.build_command("run")
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            if os.name == "nt":
                creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            self._process = subprocess.Popen(
                cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            self._last_command = cmd
            self._last_start_ts = time.time()
            self._last_exit_code = None
            self._write_lockfile()
            self._log_lines.append(f"[info] watcher started pid={self._process.pid}")
            self._pump_thread = threading.Thread(target=self._pump_output, daemon=True, name="gui-cli-pump")
            self._pump_thread.start()

    def stop_watcher(self, *, timeout_sec: float = 5.0) -> None:
        with self._lock:
            proc = self._process
            self._process = None
        if not proc:
            self._remove_lockfile()
            return
        if proc.poll() is not None:
            self._last_exit_code = proc.returncode
            self._remove_lockfile()
            return
        self._log_lines.append("[info] stopping watcher")
        try:
            if os.name == "nt":
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                proc.terminate()
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
        try:
            proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
        self._last_exit_code = proc.returncode
        self._remove_lockfile()
        self._log_lines.append(f"[info] watcher stopped exit={proc.returncode}")

    def run_once(self, subcommand: str, *extra_args: str, timeout_sec: float = 120.0) -> CommandResult:
        cmd = self.build_command(subcommand, *extra_args)
        started = time.time()
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            cmd,
            cwd=self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
            creationflags=creationflags,
        )
        finished = time.time()
        result = CommandResult(
            command=cmd,
            returncode=int(proc.returncode),
            output=proc.stdout or "",
            started_at=started,
            finished_at=finished,
        )
        output_preview = (result.output or "").strip().splitlines()[-1:] or ["(no output)"]
        self._log_lines.append(f"[oneshot:{subcommand}] rc={result.returncode} {output_preview[0]}")
        return result

    def status_snapshot(self) -> dict[str, object]:
        with self._lock:
            proc = self._process
            running = bool(proc and proc.poll() is None)
            pid = proc.pid if proc and running else None
            if proc and not running:
                self._last_exit_code = proc.returncode
                self._process = None
                self._remove_lockfile()
        return {
            "running": running,
            "pid": pid,
            "config_path": self.config_path,
            "cwd": self.cwd,
            "last_start_ts": self._last_start_ts,
            "last_exit_code": self._last_exit_code,
            "last_command": list(self._last_command),
            "lockfile_path": str(self._lockfile),
            "lockfile_exists": self._lockfile.exists(),
            "log_tail": list(self._log_lines),
        }

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.stop_watcher(timeout_sec=0.5)
        except Exception:
            pass

    def _pump_output(self) -> None:
        proc = self._process
        if not proc or not proc.stdout:
            return
        try:
            for line in proc.stdout:
                text = line.rstrip()
                if text:
                    self._log_lines.append(text)
        except Exception as exc:
            self._log_lines.append(f"[warn] output pump failed: {exc}")
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            rc = proc.poll()
            if rc is not None:
                self._last_exit_code = rc
                self._log_lines.append(f"[info] watcher exited rc={rc}")
                self._remove_lockfile()

    def _write_lockfile(self) -> None:
        try:
            self._lockfile.write_text(
                f"pid={self._process.pid if self._process else ''}\nconfig={self.config_path}\n",
                encoding="utf-8",
            )
        except Exception as exc:
            self._log_lines.append(f"[warn] lockfile write failed: {exc}")

    def _remove_lockfile(self) -> None:
        try:
            if self._lockfile.exists():
                self._lockfile.unlink()
        except Exception:
            pass

    def _warn_if_stale_lock(self) -> None:
        if self._lockfile.exists():
            self._log_lines.append(f"[warn] Existing GUI watcher lockfile detected: {self._lockfile}")
