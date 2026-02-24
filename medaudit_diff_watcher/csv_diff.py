from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from medaudit_diff_watcher.config import CsvConfig, DiffConfig
from medaudit_diff_watcher.models import (
    CellDiff,
    CsvDiffResult,
    CsvDiffSummary,
    FileSnapshot,
    SchemaDiff,
    SuspectedModifiedRow,
)
from medaudit_diff_watcher.utils import json_dumps, sha256_file


def _make_unique_headers(headers: list[str]) -> list[str]:
    seen: Counter[str] = Counter()
    unique: list[str] = []
    for h in headers:
        key = h or "unnamed"
        seen[key] += 1
        if seen[key] == 1:
            unique.append(key)
        else:
            unique.append(f"{key}__{seen[key]}")
    return unique


@dataclass(slots=True)
class _LoadedCsv:
    headers: list[str]
    rows: list[dict[str, str]]
    snapshot: FileSnapshot


class CsvDiffEngine:
    def __init__(self, csv_config: CsvConfig, diff_config: DiffConfig) -> None:
        self.csv_config = csv_config
        self.diff_config = diff_config

    def compare_files(self, left_csv: Path, right_csv: Path) -> CsvDiffResult:
        left = self._load_csv(left_csv)
        right = self._load_csv(right_csv)

        schema_diff = self._compute_schema_diff(left.headers, right.headers)
        union_headers = self._union_headers(left.headers, right.headers)

        exact_count, deleted_rows, added_rows = self._deterministic_diff(left.rows, right.rows, union_headers)

        warnings: list[str] = []
        suspected_modified: list[SuspectedModifiedRow] = []
        fuzzy_enabled = bool(self.diff_config.enable_fuzzy_match)

        if fuzzy_enabled and deleted_rows and added_rows:
            limit = self.diff_config.max_fuzzy_comparisons
            pair_count = len(deleted_rows) * len(added_rows)
            if pair_count > limit:
                warnings.append(
                    f"Skipped fuzzy matching because comparison count {pair_count} exceeds max_fuzzy_comparisons={limit}."
                )
            else:
                deleted_rows, added_rows, suspected_modified = self._fuzzy_match_rows(
                    deleted_rows,
                    added_rows,
                    union_headers,
                )

        summary = CsvDiffSummary(
            total_rows_left=len(left.rows),
            total_rows_right=len(right.rows),
            exact_match_rows=exact_count,
            added_rows=len(added_rows),
            deleted_rows=len(deleted_rows),
            suspected_modified_rows=len(suspected_modified),
            fuzzy_match_enabled=fuzzy_enabled,
        )

        return CsvDiffResult(
            left_snapshot=left.snapshot,
            right_snapshot=right.snapshot,
            schema_diff=schema_diff,
            summary=summary,
            added_rows=added_rows,
            deleted_rows=deleted_rows,
            suspected_modified_rows=suspected_modified,
            warnings=warnings,
        )

    def _load_csv(self, path: Path) -> _LoadedCsv:
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"CSV path is not a file: {path}")

        encodings = [self.csv_config.encoding] if self.csv_config.encoding != "auto" else [
            "utf-8-sig",
            "utf-8",
            "gb18030",
            "gbk",
            "big5",
            "latin-1",
        ]
        last_error: Exception | None = None
        for enc in encodings:
            try:
                with path.open("r", encoding=enc, newline="") as fh:
                    sample = fh.read(4096)
                    fh.seek(0)
                    delimiter = self._detect_delimiter(sample)
                    headers, rows = self._parse_csv(fh, delimiter)
                stat = path.stat()
                snapshot = FileSnapshot(
                    path=str(path.resolve()),
                    file_size=stat.st_size,
                    mtime=stat.st_mtime,
                    sha256=sha256_file(path),
                    encoding=enc,
                    delimiter=delimiter,
                )
                return _LoadedCsv(headers=headers, rows=rows, snapshot=snapshot)
            except UnicodeDecodeError as exc:
                last_error = exc
                continue
            except csv.Error as exc:
                last_error = exc
                continue
        raise RuntimeError(f"Failed to read CSV {path}: {last_error}")

    def _detect_delimiter(self, sample: str) -> str:
        if self.csv_config.delimiter != "auto":
            return self.csv_config.delimiter
        if not sample.strip():
            return ","
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=[",", ";", "\t", "|"])
            return dialect.delimiter
        except Exception:
            return ","

    def _parse_csv(self, fh: io.TextIOBase, delimiter: str) -> tuple[list[str], list[dict[str, str]]]:
        reader = csv.reader(fh, delimiter=delimiter)
        try:
            raw_headers = next(reader)
        except StopIteration:
            return [], []

        headers = [self._normalize_header(h) for h in raw_headers]
        headers = _make_unique_headers(headers)
        rows: list[dict[str, str]] = []
        for raw_row in reader:
            if len(raw_row) < len(headers):
                raw_row = raw_row + [""] * (len(headers) - len(raw_row))
            elif len(raw_row) > len(headers):
                raw_row = raw_row[: len(headers) - 1] + [delimiter.join(raw_row[len(headers) - 1 :])]
            normalized = {headers[i]: self._normalize_value(raw_row[i]) for i in range(len(headers))}
            rows.append(normalized)
        return headers, rows

    def _normalize_header(self, value: str) -> str:
        out = value.strip() if self.csv_config.normalize_trim_whitespace else value
        if self.csv_config.normalize_case_headers:
            out = out.lower()
        return out

    def _normalize_value(self, value: str) -> str:
        out = value
        if self.csv_config.normalize_trim_whitespace:
            out = out.strip()
        if out in self.csv_config.null_equivalents:
            return ""
        return out

    def _compute_schema_diff(self, left_headers: list[str], right_headers: list[str]) -> SchemaDiff:
        left_set = set(left_headers)
        right_set = set(right_headers)
        added = [h for h in right_headers if h not in left_set]
        removed = [h for h in left_headers if h not in right_set]
        reordered: list[str] = []
        common = [h for h in left_headers if h in right_set]
        right_positions = {h: i for i, h in enumerate(right_headers)}
        for idx, header in enumerate(common):
            if idx >= len(right_headers):
                break
            if right_positions.get(header) != idx:
                reordered.append(header)
        return SchemaDiff(
            left_headers=left_headers,
            right_headers=right_headers,
            added_columns=added,
            removed_columns=removed,
            reordered_columns=reordered,
        )

    def _union_headers(self, left_headers: list[str], right_headers: list[str]) -> list[str]:
        union = list(left_headers)
        for h in right_headers:
            if h not in union:
                union.append(h)
        return union

    def _row_canonical(self, row: dict[str, str], union_headers: list[str]) -> str:
        normalized = {h: row.get(h, "") for h in union_headers}
        return json_dumps(normalized)

    def _deterministic_diff(
        self,
        left_rows: list[dict[str, str]],
        right_rows: list[dict[str, str]],
        union_headers: list[str],
    ) -> tuple[int, list[dict[str, str]], list[dict[str, str]]]:
        left_buckets: dict[str, list[dict[str, str]]] = {}
        right_buckets: dict[str, list[dict[str, str]]] = {}

        for row in left_rows:
            key = self._row_canonical(row, union_headers)
            left_buckets.setdefault(key, []).append(row)
        for row in right_rows:
            key = self._row_canonical(row, union_headers)
            right_buckets.setdefault(key, []).append(row)

        exact_count = 0
        deleted_rows: list[dict[str, str]] = []
        added_rows: list[dict[str, str]] = []
        all_keys = set(left_buckets) | set(right_buckets)
        for key in all_keys:
            left_list = left_buckets.get(key, [])
            right_list = right_buckets.get(key, [])
            match_count = min(len(left_list), len(right_list))
            exact_count += match_count
            if len(left_list) > match_count:
                deleted_rows.extend(left_list[match_count:])
            if len(right_list) > match_count:
                added_rows.extend(right_list[match_count:])
        return exact_count, deleted_rows, added_rows

    def _similarity(self, a: str, b: str) -> float:
        try:
            from rapidfuzz import fuzz  # type: ignore

            return float(fuzz.ratio(a, b))
        except Exception:
            return SequenceMatcher(a=a, b=b).ratio() * 100.0

    def _flatten_row(self, row: dict[str, str], headers: list[str]) -> str:
        return " | ".join(f"{h}={row.get(h, '')}" for h in headers)

    def _fuzzy_match_rows(
        self,
        deleted_rows: list[dict[str, str]],
        added_rows: list[dict[str, str]],
        headers: list[str],
    ) -> tuple[list[dict[str, str]], list[dict[str, str]], list[SuspectedModifiedRow]]:
        threshold = float(self.diff_config.fuzzy_threshold)
        used_added: set[int] = set()
        matches: list[tuple[int, int, float]] = []
        deleted_flat = [self._flatten_row(r, headers) for r in deleted_rows]
        added_flat = [self._flatten_row(r, headers) for r in added_rows]

        for d_idx, d_text in enumerate(deleted_flat):
            best_idx = -1
            best_score = -1.0
            for a_idx, a_text in enumerate(added_flat):
                if a_idx in used_added:
                    continue
                score = self._similarity(d_text, a_text)
                if score > best_score:
                    best_score = score
                    best_idx = a_idx
            if best_idx >= 0 and best_score >= threshold:
                used_added.add(best_idx)
                matches.append((d_idx, best_idx, best_score))

        matched_deleted = {d for d, _, _ in matches}
        suspected: list[SuspectedModifiedRow] = []
        for idx, (d_idx, a_idx, score) in enumerate(matches, start=1):
            left_row = deleted_rows[d_idx]
            right_row = added_rows[a_idx]
            cell_diffs = [
                CellDiff(column_name=h, left_value=left_row.get(h, ""), right_value=right_row.get(h, ""))
                for h in headers
                if left_row.get(h, "") != right_row.get(h, "")
            ]
            suspected.append(
                SuspectedModifiedRow(
                    match_group_id=f"m{idx}",
                    left_row=left_row,
                    right_row=right_row,
                    confidence=round(score, 2),
                    cell_diffs=cell_diffs,
                )
            )

        remaining_deleted = [row for idx, row in enumerate(deleted_rows) if idx not in matched_deleted]
        remaining_added = [row for idx, row in enumerate(added_rows) if idx not in used_added]
        return remaining_deleted, remaining_added, suspected
