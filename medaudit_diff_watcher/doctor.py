from __future__ import annotations

import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from medaudit_diff_watcher.config import AppConfig


@dataclass(slots=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def run_doctor(config: AppConfig) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    root = Path(config.watch.root_dir).expanduser()
    checks.append(
        DoctorCheck(
            name="watch.root_dir",
            ok=root.exists() and root.is_dir(),
            detail=f"{root} ({'exists' if root.exists() else 'missing'})",
        )
    )

    db_path = Path(config.db.sqlite_path).expanduser()
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute("SELECT 1")
        checks.append(DoctorCheck(name="sqlite", ok=True, detail=str(db_path)))
    except Exception as exc:
        checks.append(DoctorCheck(name="sqlite", ok=False, detail=str(exc)))

    if config.compare_tool.enabled:
        bc_path = Path(config.compare_tool.executable_path).expanduser()
        tool_label = "compare_tool"
        tool_desc = f"{config.compare_tool.tool or 'auto'} @ {bc_path}"
        checks.append(
            DoctorCheck(
                name=tool_label,
                ok=bc_path.exists(),
                detail=tool_desc,
            )
        )
    else:
        checks.append(DoctorCheck(name="compare_tool", ok=True, detail="disabled"))

    checks.append(
        DoctorCheck(
            name="csv.fixed_filename",
            ok=bool(config.csv.fixed_filename.strip()),
            detail=config.csv.fixed_filename,
        )
    )
    exclude_patterns = [pattern for pattern in config.csv.exclude_columns_regex if pattern.strip()]
    checks.append(
        DoctorCheck(
            name="csv.exclude_columns_regex",
            ok=True,
            detail=", ".join(exclude_patterns) if exclude_patterns else "(none)",
        )
    )

    for dep_name, module_name in [
        ("yaml", "yaml"),
        ("watchdog (optional)", "watchdog"),
        ("rapidfuzz (optional)", "rapidfuzz"),
    ]:
        try:
            __import__(module_name)
            checks.append(DoctorCheck(name=dep_name, ok=True, detail="installed"))
        except Exception:
            optional = "optional" in dep_name
            checks.append(DoctorCheck(name=dep_name, ok=optional, detail="not installed"))

    if config.ai.enabled:
        ok = False
        detail = "not checked"
        if config.ai.base_url and config.ai.api_key and config.ai.model:
            try:
                req = urllib.request.Request(config.ai.base_url, method="GET")
                with urllib.request.urlopen(req, timeout=min(config.ai.timeout_sec, 10)) as resp:
                    detail = f"HTTP {resp.status}"
                    ok = True
            except urllib.error.HTTPError as exc:
                # 401/404 still proves network reachability and host responsiveness.
                detail = f"HTTP {exc.code} (reachable)"
                ok = True
            except Exception as exc:
                detail = f"connect failed: {exc}"
        else:
            detail = "missing ai.base_url / ai.api_key / ai.model"
        checks.append(DoctorCheck(name="ai_connectivity", ok=ok, detail=detail))
    else:
        checks.append(DoctorCheck(name="ai_connectivity", ok=True, detail="disabled"))

    return checks
