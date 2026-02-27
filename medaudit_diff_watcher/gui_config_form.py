from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

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


class ConfigFormWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        root.addWidget(scroll, 1)

        body = QWidget()
        scroll.setWidget(body)
        grid = QGridLayout(body)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self._build_watch_group(grid, 0, 0)
        self._build_csv_group(grid, 1, 0)
        self._build_diff_group(grid, 2, 0)
        self._build_compare_group(grid, 0, 1)
        self._build_storage_group(grid, 1, 1)
        self._build_ai_group(grid, 2, 1)

        grid.setRowStretch(3, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

    def _build_watch_group(self, grid: QGridLayout, row: int, col: int) -> None:
        box = QGroupBox("Watch")
        form = QFormLayout(box)

        root_dir_row = QHBoxLayout()
        self.watch_root_dir_edit = QLineEdit()
        btn_browse_root = QPushButton("Browse…")
        btn_browse_root.clicked.connect(self._browse_watch_root_dir)
        root_dir_row.addWidget(self.watch_root_dir_edit, 1)
        root_dir_row.addWidget(btn_browse_root)
        form.addRow("root_dir", self._wrap(root_dir_row))

        self.watch_root_dirs_edit = QPlainTextEdit()
        self.watch_root_dirs_edit.setPlaceholderText("One watch root per line (optional, enables multi-watch)")
        self.watch_root_dirs_edit.setFixedHeight(110)
        root_dirs_btns = QHBoxLayout()
        btn_add_root_dir = QPushButton("Add Folder")
        btn_add_root_dir.clicked.connect(self._append_watch_root_dir_from_dialog)
        btn_clear_root_dirs = QPushButton("Clear")
        btn_clear_root_dirs.clicked.connect(self.watch_root_dirs_edit.clear)
        root_dirs_btns.addWidget(btn_add_root_dir)
        root_dirs_btns.addWidget(btn_clear_root_dirs)
        root_dirs_btns.addStretch(1)
        root_dirs_panel = QVBoxLayout()
        root_dirs_panel.setContentsMargins(0, 0, 0, 0)
        root_dirs_panel.addWidget(self.watch_root_dirs_edit)
        root_dirs_panel.addLayout(root_dirs_btns)
        form.addRow("root_dirs", self._wrap(root_dirs_panel))

        self.watch_scan_interval_spin = QSpinBox()
        self.watch_scan_interval_spin.setRange(1, 3600)
        self.watch_stable_wait_spin = QSpinBox()
        self.watch_stable_wait_spin.setRange(0, 300)
        self.watch_min_subfolders_spin = QSpinBox()
        self.watch_min_subfolders_spin.setRange(2, 1000)
        form.addRow("scan_interval_sec", self.watch_scan_interval_spin)
        form.addRow("stable_wait_sec", self.watch_stable_wait_spin)
        form.addRow("min_subfolders_to_compare", self.watch_min_subfolders_spin)

        self.pairing_strategy_combo = QComboBox()
        self.pairing_strategy_combo.setEditable(True)
        self.pairing_strategy_combo.addItems(["latest_two"])
        form.addRow("pairing.strategy", self.pairing_strategy_combo)

        hint = QLabel("If `root_dirs` is not empty, it takes precedence over `root_dir`.")
        hint.setWordWrap(True)
        form.addRow("", hint)

        grid.addWidget(box, row, col)

    def _build_csv_group(self, grid: QGridLayout, row: int, col: int) -> None:
        box = QGroupBox("CSV")
        form = QFormLayout(box)

        self.csv_fixed_filename_edit = QLineEdit()
        self.csv_fixed_filename_edit.setPlaceholderText("Example: *.csv or DM.csv")

        self.csv_encoding_combo = QComboBox()
        self.csv_encoding_combo.setEditable(True)
        self.csv_encoding_combo.addItems(["auto", "utf-8", "utf-8-sig", "cp932", "shift_jis"])

        self.csv_delimiter_combo = QComboBox()
        self.csv_delimiter_combo.setEditable(True)
        self.csv_delimiter_combo.addItems(["auto", ",", "\t", "|", ";"])

        self.csv_trim_ws_check = QCheckBox("normalize_trim_whitespace")
        self.csv_case_headers_check = QCheckBox("normalize_case_headers")

        self.csv_null_equiv_edit = QPlainTextEdit()
        self.csv_null_equiv_edit.setPlaceholderText("One null-equivalent value per line")
        self.csv_null_equiv_edit.setFixedHeight(86)

        form.addRow("fixed_filename", self.csv_fixed_filename_edit)
        form.addRow("encoding", self.csv_encoding_combo)
        form.addRow("delimiter", self.csv_delimiter_combo)
        form.addRow("", self.csv_trim_ws_check)
        form.addRow("", self.csv_case_headers_check)
        form.addRow("null_equivalents", self.csv_null_equiv_edit)

        grid.addWidget(box, row, col)

    def _build_diff_group(self, grid: QGridLayout, row: int, col: int) -> None:
        box = QGroupBox("Diff")
        form = QFormLayout(box)

        self.diff_enable_fuzzy_check = QCheckBox("enable_fuzzy_match")
        self.diff_threshold_spin = QSpinBox()
        self.diff_threshold_spin.setRange(0, 100)
        self.diff_max_comp_spin = QSpinBox()
        self.diff_max_comp_spin.setRange(0, 10_000_000)

        form.addRow("", self.diff_enable_fuzzy_check)
        form.addRow("fuzzy_threshold", self.diff_threshold_spin)
        form.addRow("max_fuzzy_comparisons", self.diff_max_comp_spin)

        grid.addWidget(box, row, col)

    def _build_compare_group(self, grid: QGridLayout, row: int, col: int) -> None:
        box = QGroupBox("Compare Tool")
        form = QFormLayout(box)

        self.compare_enabled_check = QCheckBox("enabled")
        self.compare_tool_combo = QComboBox()
        self.compare_tool_combo.addItems(["auto", "bcompare", "winmerge"])
        self.compare_mode_combo = QComboBox()
        self.compare_mode_combo.addItems(["file", "folder"])
        self.compare_exec_path_edit = QLineEdit()
        self.compare_exec_path_edit.setPlaceholderText(r"C:\Program Files\Beyond Compare 5\BCompare.exe")
        exec_row = QHBoxLayout()
        btn_browse_compare = QPushButton("Browse…")
        btn_browse_compare.clicked.connect(self._browse_compare_executable)
        exec_row.addWidget(self.compare_exec_path_edit, 1)
        exec_row.addWidget(btn_browse_compare)

        form.addRow("", self.compare_enabled_check)
        form.addRow("tool", self.compare_tool_combo)
        form.addRow("compare_mode", self.compare_mode_combo)
        form.addRow("executable_path", self._wrap(exec_row))

        grid.addWidget(box, row, col)

    def _build_storage_group(self, grid: QGridLayout, row: int, col: int) -> None:
        box = QGroupBox("DB / Reports / Logging")
        form = QFormLayout(box)

        self.db_sqlite_path_edit = QLineEdit()
        db_row = QHBoxLayout()
        btn_browse_db = QPushButton("Browse…")
        btn_browse_db.clicked.connect(self._browse_db_path)
        db_row.addWidget(self.db_sqlite_path_edit, 1)
        db_row.addWidget(btn_browse_db)

        self.report_output_dir_edit = QLineEdit()
        report_row = QHBoxLayout()
        btn_browse_report = QPushButton("Browse…")
        btn_browse_report.clicked.connect(self._browse_report_output_dir)
        report_row.addWidget(self.report_output_dir_edit, 1)
        report_row.addWidget(btn_browse_report)

        self.logging_level_combo = QComboBox()
        self.logging_level_combo.setEditable(True)
        self.logging_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

        form.addRow("db.sqlite_path", self._wrap(db_row))
        form.addRow("report.output_dir", self._wrap(report_row))
        form.addRow("logging.level", self.logging_level_combo)

        grid.addWidget(box, row, col)

    def _build_ai_group(self, grid: QGridLayout, row: int, col: int) -> None:
        box = QGroupBox("AI (Optional / Advanced)")
        form = QFormLayout(box)

        self.ai_enabled_check = QCheckBox("enabled")
        self.ai_base_url_edit = QLineEdit()
        self.ai_api_key_edit = QLineEdit()
        self.ai_model_edit = QLineEdit()
        self.ai_timeout_spin = QSpinBox()
        self.ai_timeout_spin.setRange(1, 600)
        self.ai_retries_spin = QSpinBox()
        self.ai_retries_spin.setRange(0, 20)
        self.ai_send_raw_rows_check = QCheckBox("send_raw_rows")

        form.addRow("", self.ai_enabled_check)
        form.addRow("base_url", self.ai_base_url_edit)
        form.addRow("api_key", self.ai_api_key_edit)
        form.addRow("model", self.ai_model_edit)
        form.addRow("timeout_sec", self.ai_timeout_spin)
        form.addRow("max_retries", self.ai_retries_spin)
        form.addRow("", self.ai_send_raw_rows_check)

        note = QLabel("You can still use the YAML tab for advanced/manual edits and comments.")
        note.setWordWrap(True)
        form.addRow("", note)

        grid.addWidget(box, row, col)

    def set_config(self, cfg: AppConfig) -> None:
        self.watch_root_dir_edit.setText(cfg.watch.root_dir)
        self.watch_root_dirs_edit.setPlainText("\n".join(cfg.watch.root_dirs))
        self.watch_scan_interval_spin.setValue(int(cfg.watch.scan_interval_sec))
        self.watch_stable_wait_spin.setValue(int(cfg.watch.stable_wait_sec))
        self.watch_min_subfolders_spin.setValue(int(cfg.watch.min_subfolders_to_compare))
        self._set_combo_text(self.pairing_strategy_combo, cfg.pairing.strategy)

        self.csv_fixed_filename_edit.setText(cfg.csv.fixed_filename)
        self._set_combo_text(self.csv_encoding_combo, cfg.csv.encoding)
        self._set_combo_text(self.csv_delimiter_combo, cfg.csv.delimiter)
        self.csv_trim_ws_check.setChecked(bool(cfg.csv.normalize_trim_whitespace))
        self.csv_case_headers_check.setChecked(bool(cfg.csv.normalize_case_headers))
        self.csv_null_equiv_edit.setPlainText("\n".join(cfg.csv.null_equivalents))

        self.diff_enable_fuzzy_check.setChecked(bool(cfg.diff.enable_fuzzy_match))
        self.diff_threshold_spin.setValue(int(cfg.diff.fuzzy_threshold))
        self.diff_max_comp_spin.setValue(int(cfg.diff.max_fuzzy_comparisons))

        self.compare_enabled_check.setChecked(bool(cfg.compare_tool.enabled))
        self._set_combo_text(self.compare_tool_combo, cfg.compare_tool.tool)
        self._set_combo_text(self.compare_mode_combo, cfg.compare_tool.compare_mode)
        self.compare_exec_path_edit.setText(cfg.compare_tool.executable_path)

        self.db_sqlite_path_edit.setText(cfg.db.sqlite_path)
        self.report_output_dir_edit.setText(cfg.report.output_dir)
        self._set_combo_text(self.logging_level_combo, cfg.logging.level.upper())

        self.ai_enabled_check.setChecked(bool(cfg.ai.enabled))
        self.ai_base_url_edit.setText(cfg.ai.base_url)
        self.ai_api_key_edit.setText(cfg.ai.api_key)
        self.ai_model_edit.setText(cfg.ai.model)
        self.ai_timeout_spin.setValue(int(cfg.ai.timeout_sec))
        self.ai_retries_spin.setValue(int(cfg.ai.max_retries))
        self.ai_send_raw_rows_check.setChecked(bool(cfg.ai.send_raw_rows))

    def to_config(self) -> AppConfig:
        root_dirs = [line.strip() for line in self.watch_root_dirs_edit.toPlainText().splitlines() if line.strip()]
        null_equivs = [line.rstrip("\r") for line in self.csv_null_equiv_edit.toPlainText().splitlines()]
        if not null_equivs:
            null_equivs = ["", "NULL", "null", "N/A"]

        return AppConfig(
            watch=WatchConfig(
                root_dir=self.watch_root_dir_edit.text().strip(),
                root_dirs=root_dirs,
                scan_interval_sec=int(self.watch_scan_interval_spin.value()),
                stable_wait_sec=int(self.watch_stable_wait_spin.value()),
                min_subfolders_to_compare=int(self.watch_min_subfolders_spin.value()),
            ),
            pairing=PairingConfig(strategy=self._combo_text(self.pairing_strategy_combo) or "latest_two"),
            csv=CsvConfig(
                fixed_filename=self.csv_fixed_filename_edit.text().strip(),
                encoding=self._combo_text(self.csv_encoding_combo) or "auto",
                delimiter=self._combo_text(self.csv_delimiter_combo) or "auto",
                normalize_trim_whitespace=self.csv_trim_ws_check.isChecked(),
                normalize_case_headers=self.csv_case_headers_check.isChecked(),
                null_equivalents=[str(x) for x in null_equivs],
            ),
            diff=DiffConfig(
                enable_fuzzy_match=self.diff_enable_fuzzy_check.isChecked(),
                fuzzy_threshold=int(self.diff_threshold_spin.value()),
                max_fuzzy_comparisons=int(self.diff_max_comp_spin.value()),
            ),
            compare_tool=CompareToolConfig(
                enabled=self.compare_enabled_check.isChecked(),
                executable_path=self.compare_exec_path_edit.text().strip(),
                compare_mode=self._combo_text(self.compare_mode_combo) or "file",
                tool=self._combo_text(self.compare_tool_combo) or "auto",
            ),
            db=DBConfig(sqlite_path=self.db_sqlite_path_edit.text().strip()),
            report=ReportConfig(output_dir=self.report_output_dir_edit.text().strip()),
            ai=AIConfig(
                enabled=self.ai_enabled_check.isChecked(),
                base_url=self.ai_base_url_edit.text().strip(),
                api_key=self.ai_api_key_edit.text(),
                model=self.ai_model_edit.text().strip(),
                timeout_sec=int(self.ai_timeout_spin.value()),
                max_retries=int(self.ai_retries_spin.value()),
                send_raw_rows=self.ai_send_raw_rows_check.isChecked(),
            ),
            logging=LoggingConfig(level=(self._combo_text(self.logging_level_combo) or "INFO").upper()),
        )

    def _browse_watch_root_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select watch.root_dir", self.watch_root_dir_edit.text().strip() or str(Path.cwd()))
        if path:
            self.watch_root_dir_edit.setText(path)

    def _append_watch_root_dir_from_dialog(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Add watch.root_dirs entry",
            self.watch_root_dir_edit.text().strip() or str(Path.cwd()),
        )
        if not path:
            return
        lines = [line.strip() for line in self.watch_root_dirs_edit.toPlainText().splitlines() if line.strip()]
        if path not in lines:
            lines.append(path)
            self.watch_root_dirs_edit.setPlainText("\n".join(lines))

    def _browse_compare_executable(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select compare tool executable",
            self.compare_exec_path_edit.text().strip() or str(Path.cwd()),
            "Executable (*.exe);;All Files (*)",
        )
        if path:
            self.compare_exec_path_edit.setText(path)

    def _browse_db_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Select SQLite DB path",
            self.db_sqlite_path_edit.text().strip() or str(Path.cwd() / "data_gui_dev" / "medaudit_diff_gui.db"),
            "SQLite DB (*.db *.sqlite);;All Files (*)",
        )
        if path:
            self.db_sqlite_path_edit.setText(path)

    def _browse_report_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Select report.output_dir",
            self.report_output_dir_edit.text().strip() or str(Path.cwd()),
        )
        if path:
            self.report_output_dir_edit.setText(path)

    def _combo_text(self, combo: QComboBox) -> str:
        return combo.currentText().strip()

    def _set_combo_text(self, combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentText(value)

    def _wrap(self, layout) -> QWidget:
        widget = QWidget()
        widget.setLayout(layout)
        return widget
