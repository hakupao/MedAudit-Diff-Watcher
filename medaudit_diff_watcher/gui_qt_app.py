from __future__ import annotations

import argparse
import tempfile
import threading
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QCloseEvent, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStatusBar,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from medaudit_diff_watcher.config import AppConfig, load_config, save_config
from medaudit_diff_watcher.gui_config_form import ConfigFormWidget
from medaudit_diff_watcher.gui_support import (
    CliSubprocessController,
    clone_config_file,
    default_gui_dev_config_path,
    ensure_gui_dev_config_file,
    open_path_external,
)
from medaudit_diff_watcher.gui_yaml_highlighter import YamlSyntaxHighlighter
from medaudit_diff_watcher.repository import DiffRepository


class _Signals(QObject):
    one_shot_done = Signal(str, int, str)
    one_shot_failed = Signal(str, str)


class MainWindow(QMainWindow):
    def __init__(self, *, config_path: str | Path) -> None:
        super().__init__()
        self.setWindowTitle("MedAudit Diff Watcher GUI")
        self.resize(1200, 760)

        self.config_path = str(ensure_gui_dev_config_file(config_path))
        self.controller = CliSubprocessController(config_path=self.config_path)
        self.current_db_path = ""
        self.current_report_dir = ""
        self._quit_requested = False
        self._signals = _Signals()
        self._signals.one_shot_done.connect(self._on_one_shot_done)
        self._signals.one_shot_failed.connect(self._on_one_shot_failed)
        self._batch_rows: list[dict[str, Any]] = []
        self._job_rows: list[dict[str, Any]] = []
        self._yaml_highlighter: YamlSyntaxHighlighter | None = None

        self._build_ui()
        self._apply_ui_scaling()
        self._setup_tray()
        self._load_config_text_from_disk()
        self._refresh_status()
        self._refresh_results()

        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1500)
        self.status_timer.timeout.connect(self._refresh_status)
        self.status_timer.start()

        self.results_timer = QTimer(self)
        self.results_timer.setInterval(5000)
        self.results_timer.timeout.connect(self._refresh_results)
        self.results_timer.start()

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.control_tab = self._build_control_tab()
        self.config_form_tab = self._build_config_form_tab()
        self.config_yaml_tab = self._build_config_tab()
        self.results_tab = self._build_results_tab()
        self.tabs.addTab(self.control_tab, "Control")
        self.tabs.addTab(self.config_form_tab, "Config Form")
        self.tabs.addTab(self.config_yaml_tab, "Config YAML")
        self.tabs.addTab(self.results_tab, "Results")
        root.addWidget(self.tabs)
        self.setCentralWidget(central)

        status = QStatusBar(self)
        self.status_run = QLabel("Watcher: unknown")
        self.status_cfg = QLabel(f"Config: {self.config_path}")
        self.status_db = QLabel("DB: -")
        status.addWidget(self.status_run)
        status.addPermanentWidget(self.status_db, 1)
        status.addPermanentWidget(self.status_cfg, 2)
        self.setStatusBar(status)

    def _apply_ui_scaling(self) -> None:
        base_font = self.font()
        point_size = base_font.pointSizeF()
        if point_size <= 0:
            point_size = 10.0
        base_font.setPointSizeF(point_size + 1.0)
        self.setFont(base_font)

        self.setStyleSheet(
            """
            QWidget {
                color: #1f2937;
            }
            QTabWidget::pane {
                border: 1px solid #cfd7e3;
                border-radius: 10px;
                background: #f8fafc;
                top: -1px;
            }
            QPushButton {
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                min-height: 34px;
                padding: 5px 12px;
            }
            QPushButton:hover {
                background: #e2e8f0;
            }
            QPushButton:pressed {
                background: #d7e0ea;
            }
            QPushButton:disabled {
                color: #9ca3af;
            }
            QLineEdit, QComboBox, QSpinBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                min-height: 34px;
                padding: 3px 8px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus, QTableWidget:focus {
                border: 1px solid #5b8def;
            }
            QPlainTextEdit, QTableWidget {
                background: #ffffff;
                border: 1px solid #cfd7e3;
                border-radius: 8px;
            }
            QPlainTextEdit#yamlEditor {
                background: #f8fafc;
                selection-background-color: #bfdbfe;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #9aa8bd;
                border-radius: 4px;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #2563eb;
                border: 1px solid #2563eb;
            }
            QTabBar::tab {
                background: #e9eef5;
                border: 1px solid #cfd7e3;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                min-height: 34px;
                padding: 6px 16px;
                margin-right: 4px;
                color: #334155;
            }
            QTabBar::tab:selected {
                background: #f8fafc;
                color: #0f172a;
            }
            QTabBar::tab:!selected {
                margin-top: 4px;
            }
            QTabBar::tab:hover:!selected {
                background: #dde6f1;
            }
            QHeaderView::section {
                background: #eef2f7;
                border: 1px solid #d6dde8;
                min-height: 32px;
                padding: 4px 8px;
            }
            QGroupBox {
                border: 1px solid #d4dbe6;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #334155;
                font-weight: 600;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QStatusBar {
                background: #eef2f7;
                border-top: 1px solid #cfd7e3;
            }
            """
        )

    def _build_control_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        cfg_row = QHBoxLayout()
        self.config_path_edit = QLineEdit(self.config_path)
        self.config_path_edit.setReadOnly(True)
        btn_import = QPushButton("Import from config.yaml")
        btn_import.clicked.connect(self._import_config_copy)
        btn_reload_cfg = QPushButton("Reload Config")
        btn_reload_cfg.clicked.connect(self._load_config_text_from_disk)
        cfg_row.addWidget(QLabel("GUI config"))
        cfg_row.addWidget(self.config_path_edit, 1)
        cfg_row.addWidget(btn_import)
        cfg_row.addWidget(btn_reload_cfg)
        layout.addLayout(cfg_row)

        ctl_row = QHBoxLayout()
        self.btn_start = QPushButton("Start Watcher")
        self.btn_stop = QPushButton("Stop Watcher")
        btn_scan = QPushButton("Scan Once")
        btn_doctor = QPushButton("Doctor")
        btn_refresh_results = QPushButton("Refresh Results")
        self.btn_start.clicked.connect(self._start_watcher)
        self.btn_stop.clicked.connect(self._stop_watcher)
        btn_scan.clicked.connect(lambda: self._run_oneshot_async("scan-once"))
        btn_doctor.clicked.connect(lambda: self._run_oneshot_async("doctor"))
        btn_refresh_results.clicked.connect(self._refresh_results)
        for btn in [self.btn_start, self.btn_stop, btn_scan, btn_doctor, btn_refresh_results]:
            ctl_row.addWidget(btn)
        ctl_row.addStretch(1)
        layout.addLayout(ctl_row)

        state_row = QHBoxLayout()
        self.lbl_running = QLabel("Running: -")
        self.lbl_pid = QLabel("PID: -")
        self.lbl_last_exit = QLabel("Last exit: -")
        self.lbl_lockfile = QLabel("Lockfile: -")
        for w in [self.lbl_running, self.lbl_pid, self.lbl_last_exit, self.lbl_lockfile]:
            state_row.addWidget(w)
        state_row.addStretch(1)
        layout.addLayout(state_row)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setPlaceholderText("CLI subprocess status and output tail")
        layout.addWidget(self.log_view, 1)
        return tab

    def _build_config_form_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        btn_row = QHBoxLayout()
        btn_save_form = QPushButton("Save Form (Validate)")
        btn_save_form.clicked.connect(self._save_form_to_disk)
        btn_reload = QPushButton("Reload from File")
        btn_reload.clicked.connect(self._load_config_text_from_disk)
        btn_doctor = QPushButton("Save Form + Doctor")
        btn_doctor.clicked.connect(self._save_form_and_doctor)
        btn_apply_to_yaml = QPushButton("Reload YAML Preview")
        btn_apply_to_yaml.clicked.connect(self._reload_yaml_from_saved_file)
        for btn in [btn_save_form, btn_reload, btn_doctor, btn_apply_to_yaml]:
            btn_row.addWidget(btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        info = QLabel(
            "Graphical form for common settings. Save writes `config.gui-dev.yaml` and refreshes the YAML tab. "
            "YAML tab remains available for advanced/manual edits."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.config_form = ConfigFormWidget()
        layout.addWidget(self.config_form, 1)
        return tab

    def _build_config_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("Save YAML (Validate)")
        btn_save.clicked.connect(self._save_config_text_to_disk)
        btn_reload = QPushButton("Reload YAML")
        btn_reload.clicked.connect(self._load_config_text_from_disk)
        btn_doctor = QPushButton("Save + Doctor")
        btn_doctor.clicked.connect(self._save_and_doctor)
        for btn in [btn_save, btn_reload, btn_doctor]:
            btn_row.addWidget(btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        info = QLabel(
            "Zero-impact rule: use this GUI config (default `config.gui-dev.yaml`) with separate watch/db/reports paths. "
            "Do not monitor the same folder from CLI and GUI at the same time."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.yaml_editor = QPlainTextEdit()
        self.yaml_editor.setObjectName("yamlEditor")
        self.yaml_editor.setFont(self._yaml_editor_font())
        self.yaml_editor.setTabStopDistance(float(self.yaml_editor.fontMetrics().horizontalAdvance(" ") * 4))
        self._yaml_highlighter = YamlSyntaxHighlighter(self.yaml_editor.document())
        layout.addWidget(self.yaml_editor, 1)
        return tab

    def _yaml_editor_font(self) -> QFont:
        preferred_families = [
            "Cascadia Code",
            "JetBrains Mono",
            "Fira Code",
            "Source Code Pro",
            "IBM Plex Mono",
            "Hack",
            "Consolas",
        ]
        db = QFontDatabase()
        available = {family.lower(): family for family in db.families()}
        selected_family = next((available[name.lower()] for name in preferred_families if name.lower() in available), None)
        font = QFont(selected_family) if selected_family else QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        size = font.pointSizeF()
        if size <= 0:
            size = 11.0
        font.setPointSizeF(max(12.0, size))
        font.setStyleHint(QFont.StyleHint.Monospace)
        return font

    def _build_results_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top = QHBoxLayout()
        self.results_db_path_edit = QLineEdit()
        self.results_db_path_edit.setReadOnly(True)
        top.addWidget(QLabel("DB"))
        top.addWidget(self.results_db_path_edit, 1)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_results)
        top.addWidget(btn_refresh)
        layout.addLayout(top)

        self.batch_table = QTableWidget(0, 7)
        self.batch_table.setHorizontalHeaderLabels(["ID", "Created", "Status", "Trigger", "Jobs", "Batch", "Batch Index HTML"])
        self.batch_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.batch_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.batch_table.itemSelectionChanged.connect(self._load_jobs_for_selected_batch)
        layout.addWidget(QLabel("Batches"))
        layout.addWidget(self.batch_table, 1)

        batch_btns = QHBoxLayout()
        for text, handler in [
            ("Open Batch Index", self._open_batch_index),
            ("Open Batch CSV", self._open_batch_csv),
            ("Open Batch AI", self._open_batch_ai),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            batch_btns.addWidget(btn)
        batch_btns.addStretch(1)
        layout.addLayout(batch_btns)

        self.job_table = QTableWidget(0, 10)
        self.job_table.setHorizontalHeaderLabels(
            ["Job", "Status", "Created", "File", "Exact", "Added", "Deleted", "Suspected", "Detail HTML", "Row CSV"]
        )
        self.job_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.job_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(QLabel("Jobs"))
        layout.addWidget(self.job_table, 1)

        job_btns = QHBoxLayout()
        for text, handler in [
            ("Open Detail HTML", self._open_job_detail),
            ("Open Row CSV", self._open_job_csv),
            ("Open AI Summary", self._open_job_ai),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(handler)
            job_btns.addWidget(btn)
        job_btns.addStretch(1)
        layout.addLayout(job_btns)
        return tab

    def _import_config_copy(self) -> None:
        default_src = str(Path("config.yaml").resolve())
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Import source config",
            default_src if Path(default_src).exists() else str(Path.cwd()),
            "YAML Files (*.yaml *.yml);;All Files (*)",
        )
        if not src:
            return
        try:
            clone_config_file(src, self.config_path, overwrite=True)
        except Exception as exc:
            QMessageBox.critical(self, "Import failed", str(exc))
            return
        self._append_log(f"[ui] imported config copy: {src} -> {self.config_path}")
        self._load_config_text_from_disk()

    def _load_config_text_from_disk(self) -> None:
        try:
            ensure_gui_dev_config_file(self.config_path)
            text = Path(self.config_path).read_text(encoding="utf-8")
            self.yaml_editor.setPlainText(text)
            self._refresh_config_metadata()
            self._append_log(f"[ui] loaded config text: {self.config_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load config failed", str(exc))

    def _save_config_text_to_disk(self) -> bool:
        raw = self.yaml_editor.toPlainText()
        tmp_path: Path | None = None
        try:
            target = Path(self.config_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".yaml") as fh:
                fh.write(raw)
                tmp_path = Path(fh.name)
            cfg = load_config(tmp_path)
            target.write_text(raw, encoding="utf-8")
            self._refresh_config_metadata(loaded_cfg=cfg)
            self._append_log(f"[ui] saved config: {self.config_path}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save config failed", str(exc))
            return False
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def _save_and_doctor(self) -> None:
        if self._save_config_text_to_disk():
            self._run_oneshot_async("doctor")

    def _save_form_to_disk(self) -> bool:
        tmp_path: Path | None = None
        try:
            cfg = self.config_form.to_config()
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".yaml") as fh:
                tmp_path = Path(fh.name)
            save_config(tmp_path, cfg)
            validated = load_config(tmp_path)
            target = Path(self.config_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(tmp_path.read_text(encoding="utf-8"), encoding="utf-8")
            self._refresh_config_metadata(loaded_cfg=validated)
            self.yaml_editor.setPlainText(target.read_text(encoding="utf-8"))
            self._append_log(f"[ui] saved form config: {self.config_path}")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save form failed", str(exc))
            return False
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    def _save_form_and_doctor(self) -> None:
        if self._save_form_to_disk():
            self._run_oneshot_async("doctor")

    def _reload_yaml_from_saved_file(self) -> None:
        self._load_config_text_from_disk()

    def _refresh_config_metadata(self, *, loaded_cfg: AppConfig | None = None) -> AppConfig | None:
        try:
            cfg = loaded_cfg or load_config(self.config_path)
        except Exception as exc:
            self.current_db_path = ""
            self.current_report_dir = ""
            self.status_db.setText("DB: (invalid config)")
            self._append_log(f"[warn] config metadata refresh failed: {exc}")
            return None
        self.current_db_path = cfg.db.sqlite_path
        self.current_report_dir = cfg.report.output_dir
        self.results_db_path_edit.setText(self.current_db_path)
        self.status_db.setText(f"DB: {self.current_db_path}")
        if hasattr(self, "config_form"):
            self.config_form.set_config(cfg)
        return cfg

    def _start_watcher(self) -> None:
        active_tab = self.tabs.currentWidget()
        if active_tab is self.config_form_tab:
            if not self._save_form_to_disk():
                return
        else:
            if not self._save_config_text_to_disk():
                return
        try:
            self.controller.start_watcher()
        except Exception as exc:
            QMessageBox.critical(self, "Start watcher failed", str(exc))
            return
        self._append_log("[ui] watcher start requested")
        self._show_tray_message("Watcher Started", "CLI watcher subprocess started.")
        self._refresh_status()

    def _stop_watcher(self) -> None:
        try:
            self.controller.stop_watcher()
        except Exception as exc:
            QMessageBox.critical(self, "Stop watcher failed", str(exc))
            return
        self._append_log("[ui] watcher stop requested")
        self._show_tray_message("Watcher Stopped", "CLI watcher subprocess stopped.")
        self._refresh_status()

    def _run_oneshot_async(self, subcommand: str) -> None:
        self._append_log(f"[ui] running {subcommand}")

        def _worker() -> None:
            try:
                result = self.controller.run_once(subcommand)
                self._signals.one_shot_done.emit(subcommand, result.returncode, result.output)
            except Exception as exc:
                self._signals.one_shot_failed.emit(subcommand, str(exc))

        threading.Thread(target=_worker, daemon=True, name=f"gui-{subcommand}").start()

    def _on_one_shot_done(self, subcommand: str, rc: int, output: str) -> None:
        self._append_log(f"[oneshot:{subcommand}] rc={rc}")
        if len(output) > 4000:
            output = output[:4000] + "\n...(truncated)"
        QMessageBox.information(self, f"{subcommand} (rc={rc})", output or "(no output)")
        if subcommand == "scan-once":
            self._refresh_results()

    def _on_one_shot_failed(self, subcommand: str, error_text: str) -> None:
        self._append_log(f"[oneshot:{subcommand}] failed: {error_text}")
        QMessageBox.critical(self, f"{subcommand} failed", error_text)

    def _refresh_status(self) -> None:
        status = self.controller.status_snapshot()
        running = bool(status.get("running"))
        self.status_run.setText(f"Watcher: {'running' if running else 'stopped'}")
        self.lbl_running.setText(f"Running: {'Yes' if running else 'No'}")
        self.lbl_pid.setText(f"PID: {status.get('pid') or '-'}")
        self.lbl_last_exit.setText(f"Last exit: {status.get('last_exit_code') if status.get('last_exit_code') is not None else '-'}")
        lock_path = str(status.get("lockfile_path") or "-")
        self.lbl_lockfile.setText(f"Lockfile: {lock_path}")
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)

        log_tail = status.get("log_tail") or []
        if isinstance(log_tail, list):
            self.log_view.setPlainText("\n".join(str(x) for x in log_tail[-200:]))
            sb = self.log_view.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _refresh_results(self) -> None:
        db_path = Path(self.current_db_path or self.results_db_path_edit.text().strip())
        self.results_db_path_edit.setText(str(db_path))
        if not str(db_path).strip() or not db_path.exists():
            self._batch_rows = []
            self._job_rows = []
            self._render_batches()
            self._render_jobs()
            return
        try:
            repo = DiffRepository(str(db_path))
            self._batch_rows = repo.list_batches(limit=200)
            selected_batch_id = self._selected_batch_id()
            self._render_batches(selected_batch_id=selected_batch_id)
            if selected_batch_id is not None:
                self._job_rows = repo.list_jobs(limit=500, batch_id=selected_batch_id)
            else:
                self._job_rows = []
            self._render_jobs()
        except Exception as exc:
            self._append_log(f"[results] refresh failed: {exc}")

    def _render_batches(self, *, selected_batch_id: int | None = None) -> None:
        self.batch_table.setRowCount(len(self._batch_rows))
        for r, row in enumerate(self._batch_rows):
            vals = [
                row.get("id"),
                row.get("created_at"),
                row.get("status"),
                row.get("trigger_reason"),
                f"{row.get('completed_job_count', 0)}/{row.get('job_count', 0)}",
                row.get("batch_slug"),
                row.get("batch_index_html_path") or row.get("summary_html_path") or "",
            ]
            for c, v in enumerate(vals):
                self.batch_table.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
            if selected_batch_id is not None and int(row.get("id") or 0) == int(selected_batch_id):
                self.batch_table.selectRow(r)
        self.batch_table.resizeColumnsToContents()

    def _render_jobs(self) -> None:
        self.job_table.setRowCount(len(self._job_rows))
        for r, row in enumerate(self._job_rows):
            vals = [
                row.get("id"),
                row.get("status"),
                row.get("created_at"),
                row.get("file_name"),
                row.get("exact_match_rows"),
                row.get("added_rows"),
                row.get("deleted_rows"),
                row.get("suspected_modified_rows"),
                row.get("detailed_report_path"),
                row.get("row_diffs_csv_path"),
            ]
            for c, v in enumerate(vals):
                self.job_table.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
        self.job_table.resizeColumnsToContents()

    def _selected_batch_id(self) -> int | None:
        sel = self.batch_table.selectionModel()
        rows = sel.selectedRows() if sel else []
        if not rows:
            return None
        idx = rows[0].row()
        if 0 <= idx < len(self._batch_rows):
            return int(self._batch_rows[idx]["id"])
        return None

    def _selected_batch_row(self) -> dict[str, Any] | None:
        batch_id = self._selected_batch_id()
        if batch_id is None:
            return None
        for row in self._batch_rows:
            if int(row.get("id") or 0) == batch_id:
                return row
        return None

    def _selected_job_row(self) -> dict[str, Any] | None:
        sel = self.job_table.selectionModel()
        rows = sel.selectedRows() if sel else []
        if not rows:
            return None
        idx = rows[0].row()
        return self._job_rows[idx] if 0 <= idx < len(self._job_rows) else None

    def _load_jobs_for_selected_batch(self) -> None:
        batch_id = self._selected_batch_id()
        db_path = Path(self.current_db_path or self.results_db_path_edit.text().strip())
        if batch_id is None or not db_path.exists():
            self._job_rows = []
            self._render_jobs()
            return
        try:
            repo = DiffRepository(str(db_path))
            self._job_rows = repo.list_jobs(limit=500, batch_id=batch_id)
            self._render_jobs()
        except Exception as exc:
            self._append_log(f"[results] jobs load failed: {exc}")

    def _open_batch_index(self) -> None:
        self._open_batch_path("batch_index_html_path", fallback="summary_html_path")

    def _open_batch_csv(self) -> None:
        self._open_batch_path("batch_summary_csv_path", fallback="summary_csv_path")

    def _open_batch_ai(self) -> None:
        self._open_batch_path("batch_ai_summary_md_path")

    def _open_batch_path(self, key: str, *, fallback: str | None = None) -> None:
        row = self._selected_batch_row()
        if not row:
            QMessageBox.information(self, "Open report", "Select a batch first.")
            return
        path = row.get(key) or (row.get(fallback) if fallback else None)
        if not path:
            QMessageBox.information(self, "Open report", f"No path for {key}.")
            return
        try:
            open_path_external(str(path))
        except Exception as exc:
            QMessageBox.critical(self, "Open report failed", str(exc))

    def _open_job_detail(self) -> None:
        self._open_job_path("detailed_report_path")

    def _open_job_csv(self) -> None:
        self._open_job_path("row_diffs_csv_path")

    def _open_job_ai(self) -> None:
        self._open_job_path("ai_summary_md_path")

    def _open_job_path(self, key: str) -> None:
        row = self._selected_job_row()
        if not row:
            QMessageBox.information(self, "Open report", "Select a job first.")
            return
        path = row.get(key)
        if not path:
            QMessageBox.information(self, "Open report", f"No path for {key}.")
            return
        try:
            open_path_external(str(path))
        except Exception as exc:
            QMessageBox.critical(self, "Open report failed", str(exc))

    def _append_log(self, line: str) -> None:
        text = self.log_view.toPlainText()
        lines = text.splitlines() if text else []
        lines.append(line)
        self.log_view.setPlainText("\n".join(lines[-300:]))
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _setup_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("MedAudit Diff Watcher GUI")
        self.tray.setContextMenu(self._build_tray_menu())
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _build_tray_menu(self) -> QMenu:
        menu = QMenu(self)
        for text, handler in [
            ("Show / Hide", self._toggle_visible),
            ("Start Watcher", self._start_watcher),
            ("Stop Watcher", self._stop_watcher),
            ("Scan Once", lambda: self._run_oneshot_async("scan-once")),
            ("Doctor", lambda: self._run_oneshot_async("doctor")),
        ]:
            act = QAction(text, self)
            act.triggered.connect(handler)
            menu.addAction(act)
        menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.triggered.connect(self._quit_application)
        menu.addAction(act_quit)
        return menu

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_visible()

    def _toggle_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def _show_tray_message(self, title: str, body: str) -> None:
        if self.tray and self.tray.isVisible():
            self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 2500)

    def _quit_application(self) -> None:
        self._quit_requested = True
        self.controller.stop_watcher()
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._quit_requested or not self.tray or not self.tray.isVisible():
            self.controller.stop_watcher()
            super().closeEvent(event)
            return
        self.hide()
        self._show_tray_message("Still running", "App minimized to system tray.")
        event.ignore()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="medaudit-diff-watcher-gui")
    default_cfg = str(default_gui_dev_config_path())
    parser.add_argument("--config", default=default_cfg, help=f"GUI-only config path (default: {default_cfg})")
    parser.add_argument("--hide", action="store_true", help="Start hidden (tray)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    app = QApplication.instance() or QApplication([])
    win = MainWindow(config_path=args.config)
    if args.hide and getattr(win, "tray", None):
        win.hide()
    else:
        win.show()
    return int(app.exec())
