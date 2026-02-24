from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class FileSnapshot:
    path: str
    file_size: int
    mtime: float
    sha256: str
    encoding: str = ""
    delimiter: str = ""


@dataclass(slots=True)
class SchemaDiff:
    left_headers: list[str]
    right_headers: list[str]
    added_columns: list[str]
    removed_columns: list[str]
    reordered_columns: list[str]


@dataclass(slots=True)
class CellDiff:
    column_name: str
    left_value: str
    right_value: str


@dataclass(slots=True)
class SuspectedModifiedRow:
    match_group_id: str
    left_row: dict[str, str]
    right_row: dict[str, str]
    confidence: float
    cell_diffs: list[CellDiff] = field(default_factory=list)


@dataclass(slots=True)
class CsvDiffSummary:
    total_rows_left: int
    total_rows_right: int
    exact_match_rows: int
    added_rows: int
    deleted_rows: int
    suspected_modified_rows: int
    fuzzy_match_enabled: bool


@dataclass(slots=True)
class CsvDiffResult:
    left_snapshot: FileSnapshot
    right_snapshot: FileSnapshot
    schema_diff: SchemaDiff
    summary: CsvDiffSummary
    added_rows: list[dict[str, str]]
    deleted_rows: list[dict[str, str]]
    suspected_modified_rows: list[SuspectedModifiedRow]
    warnings: list[str] = field(default_factory=list)

    def to_ai_payload(self, *, include_raw_rows: bool = False) -> dict[str, Any]:
        column_change_counts: Counter[str] = Counter()
        value_transition_counts: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
        total_cell_diffs = 0
        for row in self.suspected_modified_rows:
            for cell in row.cell_diffs:
                total_cell_diffs += 1
                column_change_counts[cell.column_name] += 1
                value_transition_counts[cell.column_name][(cell.left_value, cell.right_value)] += 1

        field_change_patterns: list[dict[str, Any]] = []
        for column_name, changed_row_count in sorted(column_change_counts.items(), key=lambda item: (-item[1], item[0])):
            transitions = value_transition_counts[column_name]
            top_transitions = [
                {
                    "left_value": left_value,
                    "right_value": right_value,
                    "count": count,
                }
                for (left_value, right_value), count in sorted(
                    transitions.items(),
                    key=lambda item: (-item[1], item[0][0], item[0][1]),
                )[:10]
            ]
            field_change_patterns.append(
                {
                    "column_name": column_name,
                    "changed_row_count": changed_row_count,
                    "unique_value_transition_count": len(transitions),
                    "top_value_transitions": top_transitions,
                }
            )

        payload: dict[str, Any] = {
            "summary": {
                "total_rows_left": self.summary.total_rows_left,
                "total_rows_right": self.summary.total_rows_right,
                "exact_match_rows": self.summary.exact_match_rows,
                "added_rows": self.summary.added_rows,
                "deleted_rows": self.summary.deleted_rows,
                "suspected_modified_rows": self.summary.suspected_modified_rows,
                "fuzzy_match_enabled": self.summary.fuzzy_match_enabled,
            },
            "schema_diff": {
                "added_columns": self.schema_diff.added_columns,
                "removed_columns": self.schema_diff.removed_columns,
                "reordered_columns": self.schema_diff.reordered_columns,
                "left_header_count": len(self.schema_diff.left_headers),
                "right_header_count": len(self.schema_diff.right_headers),
            },
            "field_change_patterns": {
                "total_cell_diffs_in_suspected_rows": total_cell_diffs,
                "columns": field_change_patterns,
            },
            "warnings": self.warnings,
            "samples": {
                "suspected_modified_rows": [
                    {
                        "changed_columns": [c.column_name for c in row.cell_diffs],
                    }
                    for row in self.suspected_modified_rows[:10]
                ]
            },
        }
        if include_raw_rows:
            payload["samples"]["added_rows"] = self.added_rows[:5]
            payload["samples"]["deleted_rows"] = self.deleted_rows[:5]
            payload["samples"]["suspected_modified_details"] = [
                {
                    "left_row": row.left_row,
                    "right_row": row.right_row,
                    "cell_diffs": [
                        {
                            "column_name": c.column_name,
                            "left_value": c.left_value,
                            "right_value": c.right_value,
                        }
                        for c in row.cell_diffs
                    ],
                }
                for row in self.suspected_modified_rows[:5]
            ]
        return payload


@dataclass(slots=True)
class PlannedComparison:
    left_folder: Path
    right_folder: Path
    left_csv: Path
    right_csv: Path
    sort_key_left: tuple[float, str]
    sort_key_right: tuple[float, str]


@dataclass(slots=True)
class LaunchResult:
    launched: bool
    command: list[str]
    error: str | None = None


@dataclass(slots=True)
class AISummaryResult:
    summary_text: str
    model: str
    prompt_version: str
    token_usage_json: str


@dataclass(slots=True)
class BatchJobSummaryRow:
    job_id: int
    file_name: str
    file_stem_dir: str
    status: str
    left_csv_path: str
    right_csv_path: str
    created_at: str
    total_rows_left: int | None = None
    total_rows_right: int | None = None
    exact_match_rows: int | None = None
    added_rows: int | None = None
    deleted_rows: int | None = None
    suspected_modified_rows: int | None = None
    added_columns_count: int | None = None
    removed_columns_count: int | None = None
    reordered_columns_count: int | None = None
    detailed_report_relpath: str | None = None
    row_diffs_relpath: str | None = None
    ai_summary_relpath: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class BatchExecutionResult:
    batch_id: int
    batch_slug: str
    trigger_reason: str
    left_folder: str
    right_folder: str
    job_rows: list[BatchJobSummaryRow] = field(default_factory=list)

    @property
    def job_ids(self) -> list[int]:
        return [row.job_id for row in self.job_rows]
