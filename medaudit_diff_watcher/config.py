from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from medaudit_diff_watcher.utils import safe_filename


@dataclass(slots=True)
class WatchConfig:
    root_dir: str = ""
    root_dirs: list[str] = field(default_factory=list)
    scan_interval_sec: int = 30
    stable_wait_sec: int = 5
    min_subfolders_to_compare: int = 2

    def effective_root_dirs(self) -> list[str]:
        if self.root_dirs:
            return [str(x).strip() for x in self.root_dirs if str(x).strip()]
        if str(self.root_dir).strip():
            return [str(self.root_dir).strip()]
        return []


@dataclass(slots=True)
class PairingConfig:
    strategy: str = "latest_two"


@dataclass(slots=True)
class CsvConfig:
    fixed_filename: str
    encoding: str = "auto"
    delimiter: str = "auto"
    normalize_trim_whitespace: bool = True
    normalize_case_headers: bool = False
    null_equivalents: list[str] = field(default_factory=lambda: ["", "NULL", "null", "N/A"])


@dataclass(slots=True)
class DiffConfig:
    enable_fuzzy_match: bool = True
    fuzzy_threshold: int = 90
    max_fuzzy_comparisons: int = 50000


@dataclass(slots=True)
class CompareToolConfig:
    enabled: bool = True
    executable_path: str = ""
    compare_mode: str = "file"  # file | folder
    tool: str = "auto"  # auto | bcompare | winmerge


@dataclass(slots=True)
class DBConfig:
    sqlite_path: str = "data/medaudit_diff.db"


@dataclass(slots=True)
class ReportConfig:
    output_dir: str = "reports"


@dataclass(slots=True)
class AIConfig:
    enabled: bool = False
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_sec: int = 30
    max_retries: int = 2
    send_raw_rows: bool = False


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(slots=True)
class AppConfig:
    watch: WatchConfig
    pairing: PairingConfig
    csv: CsvConfig
    diff: DiffConfig
    compare_tool: CompareToolConfig
    db: DBConfig
    report: ReportConfig
    ai: AIConfig
    logging: LoggingConfig

    def ensure_runtime_dirs(self) -> None:
        Path(self.db.sqlite_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        Path(self.report.output_dir).expanduser().resolve().mkdir(parents=True, exist_ok=True)


@dataclass(slots=True)
class WatchScope:
    name: str
    config: AppConfig


def _require_mapping(raw: Any, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"Expected mapping at '{path}', got {type(raw).__name__}")
    return raw


def _get(raw: dict[str, Any], key: str, default: Any = None, *, required: bool = False) -> Any:
    if key in raw:
        return raw[key]
    if required:
        raise ValueError(f"Missing required config key: {key}")
    return default


def _bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return bool(v)


def _build_config(raw: dict[str, Any]) -> AppConfig:
    watch_raw = _require_mapping(_get(raw, "watch", {}, required=True), "watch")
    pairing_raw = _require_mapping(_get(raw, "pairing", {}), "pairing")
    csv_raw = _require_mapping(_get(raw, "csv", {}, required=True), "csv")
    diff_raw = _require_mapping(_get(raw, "diff", {}), "diff")
    compare_tool_raw = _require_mapping(_get(raw, "compare_tool", {}), "compare_tool")
    db_raw = _require_mapping(_get(raw, "db", {}), "db")
    report_raw = _require_mapping(_get(raw, "report", {}), "report")
    ai_raw = _require_mapping(_get(raw, "ai", {}), "ai")
    logging_raw = _require_mapping(_get(raw, "logging", {}), "logging")

    csv_fixed_filename = str(_get(csv_raw, "fixed_filename", "", required=True)).strip()
    if not csv_fixed_filename:
        raise ValueError("csv.fixed_filename must not be empty")

    null_equivalents = _get(csv_raw, "null_equivalents", ["", "NULL", "null", "N/A"])
    if not isinstance(null_equivalents, list):
        raise ValueError("csv.null_equivalents must be a list")

    root_dirs_raw = _get(watch_raw, "root_dirs", [])
    if root_dirs_raw is None:
        root_dirs_raw = []
    if not isinstance(root_dirs_raw, list):
        raise ValueError("watch.root_dirs must be a list")
    root_dir = str(_get(watch_raw, "root_dir", "")).strip()
    root_dirs = [str(x).strip() for x in root_dirs_raw if str(x).strip()]
    if not root_dirs and not root_dir:
        raise ValueError("watch.root_dir or watch.root_dirs must provide at least one path")

    return AppConfig(
        watch=WatchConfig(
            root_dir=root_dir,
            root_dirs=root_dirs,
            scan_interval_sec=int(_get(watch_raw, "scan_interval_sec", 30)),
            stable_wait_sec=int(_get(watch_raw, "stable_wait_sec", 5)),
            min_subfolders_to_compare=int(_get(watch_raw, "min_subfolders_to_compare", 2)),
        ),
        pairing=PairingConfig(
            strategy=str(_get(pairing_raw, "strategy", "latest_two")),
        ),
        csv=CsvConfig(
            fixed_filename=csv_fixed_filename,
            encoding=str(_get(csv_raw, "encoding", "auto")),
            delimiter=str(_get(csv_raw, "delimiter", "auto")),
            normalize_trim_whitespace=_bool(_get(csv_raw, "normalize_trim_whitespace", True)),
            normalize_case_headers=_bool(_get(csv_raw, "normalize_case_headers", False)),
            null_equivalents=[str(x) for x in null_equivalents],
        ),
        diff=DiffConfig(
            enable_fuzzy_match=_bool(_get(diff_raw, "enable_fuzzy_match", True)),
            fuzzy_threshold=int(_get(diff_raw, "fuzzy_threshold", 90)),
            max_fuzzy_comparisons=int(_get(diff_raw, "max_fuzzy_comparisons", 50000)),
        ),
        compare_tool=CompareToolConfig(
            enabled=_bool(_get(compare_tool_raw, "enabled", True)),
            executable_path=str(_get(compare_tool_raw, "executable_path", "")),
            compare_mode=str(_get(compare_tool_raw, "compare_mode", "file")),
            tool=str(_get(compare_tool_raw, "tool", "auto")),
        ),
        db=DBConfig(sqlite_path=str(_get(db_raw, "sqlite_path", "data/medaudit_diff.db"))),
        report=ReportConfig(output_dir=str(_get(report_raw, "output_dir", "reports"))),
        ai=AIConfig(
            enabled=_bool(_get(ai_raw, "enabled", False)),
            base_url=str(_get(ai_raw, "base_url", "")),
            api_key=str(_get(ai_raw, "api_key", "")),
            model=str(_get(ai_raw, "model", "")),
            timeout_sec=int(_get(ai_raw, "timeout_sec", 30)),
            max_retries=int(_get(ai_raw, "max_retries", 2)),
            send_raw_rows=_bool(_get(ai_raw, "send_raw_rows", False)),
        ),
        logging=LoggingConfig(level=str(_get(logging_raw, "level", "INFO")).upper()),
    )


def load_config(path: str | Path) -> AppConfig:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency issue path
        raise RuntimeError("PyYAML is required to load config.yaml. Install with `pip install PyYAML`.") from exc

    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    if not isinstance(raw, dict):
        raise ValueError("Top-level config must be a mapping")
    config = _build_config(raw)
    config.ensure_runtime_dirs()
    return config


def expand_watch_scopes(config: AppConfig) -> list[WatchScope]:
    roots = config.watch.effective_root_dirs()
    if not roots:
        return []

    use_namespaced_storage = bool(config.watch.root_dirs)
    if not use_namespaced_storage and len(roots) == 1:
        single = copy.deepcopy(config)
        single.watch.root_dir = roots[0]
        single.watch.root_dirs = []
        single.ensure_runtime_dirs()
        return [WatchScope(name="default", config=single)]

    base_db = Path(config.db.sqlite_path).expanduser()
    base_report = Path(config.report.output_dir).expanduser()
    scopes: list[WatchScope] = []
    used_names: set[str] = set()
    for root in roots:
        watch_name = _allocate_watch_name(root, used_names)
        scoped = copy.deepcopy(config)
        scoped.watch.root_dir = root
        scoped.watch.root_dirs = [root]
        scoped.db.sqlite_path = str(base_db.parent / watch_name / base_db.name)
        scoped.report.output_dir = str(base_report / watch_name)
        scoped.ensure_runtime_dirs()
        scopes.append(WatchScope(name=watch_name, config=scoped))
    return scopes


def _allocate_watch_name(root: str, used_names: set[str]) -> str:
    p = Path(root).expanduser()
    base = safe_filename(p.name or str(p).replace(":", "_"))
    candidate = base
    idx = 2
    used_lower = {x.lower() for x in used_names}
    while candidate.lower() in used_lower:
        candidate = f"{base}__{idx}"
        idx += 1
    used_names.add(candidate)
    return candidate
