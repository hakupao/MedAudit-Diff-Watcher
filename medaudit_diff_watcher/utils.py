from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_now_compact_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    p = Path(path)
    h = hashlib.sha256()
    with p.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def safe_filename(value: str) -> str:
    banned = '<>:"/\\|?*'
    out = "".join("_" if c in banned else c for c in value)
    out = out.strip().strip(".")
    return out or "untitled"


def truncate_text(value: str, max_len: int = 200) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 3] + "..."
