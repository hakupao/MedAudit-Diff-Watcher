from __future__ import annotations

import sqlite3
import time
import traceback
from pathlib import Path

from medaudit_diff_watcher.ai_client import AISummaryClient
from medaudit_diff_watcher.compare_tool_launcher import CompareToolLauncher
from medaudit_diff_watcher.csv_diff import CsvDiffEngine
from medaudit_diff_watcher.models import (
    BatchExecutionResult,
    BatchJobSummaryRow,
    CsvDiffResult,
    PlannedComparison,
)
from medaudit_diff_watcher.planner import JobPlanner
from medaudit_diff_watcher.reporting import DetailedReportRenderer
from medaudit_diff_watcher.repository import DiffRepository
from medaudit_diff_watcher.utils import local_now_compact_timestamp, safe_filename


class PipelineRunner:
    def __init__(
        self,
        *,
        planner: JobPlanner,
        repo: DiffRepository,
        diff_engine: CsvDiffEngine,
        compare_tool_launcher: CompareToolLauncher,
        report_renderer: DetailedReportRenderer,
        ai_client: AISummaryClient,
    ) -> None:
        self.planner = planner
        self.repo = repo
        self.diff_engine = diff_engine
        self.compare_tool_launcher = compare_tool_launcher
        self.report_renderer = report_renderer
        self.ai_client = ai_client
        self.last_batch_result: BatchExecutionResult | None = None

    def process_latest_pair(self, trigger_reason: str = "scan") -> int | None:
        job_ids = self.process_latest_pairs(trigger_reason=trigger_reason)
        if not job_ids:
            return None
        return job_ids[0]

    def process_latest_pairs(self, trigger_reason: str = "scan") -> list[int]:
        plans = self.planner.plan_latest_pairs()
        if not plans:
            self.last_batch_result = None
            return []
        return self.process_plans(plans, trigger_reason=trigger_reason)

    def process_manual_pair(self, left_dir: str | Path, right_dir: str | Path, trigger_reason: str = "manual") -> int:
        job_ids = self.process_manual_pairs(left_dir, right_dir, trigger_reason=trigger_reason)
        if not job_ids:
            raise RuntimeError("No CSV comparison plans were generated for the provided folders.")
        return job_ids[0]

    def process_manual_pairs(
        self,
        left_dir: str | Path,
        right_dir: str | Path,
        trigger_reason: str = "manual",
    ) -> list[int]:
        left = Path(left_dir).expanduser().resolve()
        right = Path(right_dir).expanduser().resolve()
        plans = self.planner.build_plans_for_pair(left, right)
        if not plans:
            raise FileNotFoundError(
                self._build_no_matching_csv_message(left, right, self.planner.config.csv.fixed_filename)
            )
        return self.process_plans(plans, trigger_reason=trigger_reason)

    def process_plans(self, plans: list[PlannedComparison], *, trigger_reason: str) -> list[int]:
        if not plans:
            self.last_batch_result = None
            return []

        batch_slug, batch_id = self._create_unique_batch(
            trigger_reason=trigger_reason,
            left_folder=str(plans[0].left_folder),
            right_folder=str(plans[0].right_folder),
        )
        batch_result = BatchExecutionResult(
            batch_id=batch_id,
            batch_slug=batch_slug,
            trigger_reason=trigger_reason,
            left_folder=str(plans[0].left_folder),
            right_folder=str(plans[0].right_folder),
        )
        self.last_batch_result = batch_result

        launch_folder_bc_once = (
            len(plans) > 1 and self.compare_tool_launcher.config.compare_mode.lower().strip() == "folder"
        )
        used_dirs: set[str] = set()
        for idx, plan in enumerate(plans):
            should_launch_bc = not (launch_folder_bc_once and idx > 0)
            file_subdir = self._allocate_file_subdir(plan.left_csv, used_dirs)
            row = self.process_planned_pair(
                plan,
                trigger_reason=trigger_reason,
                launch_bc=should_launch_bc,
                batch_id=batch_id,
                batch_slug=batch_slug,
                file_subdir=file_subdir,
            )
            batch_result.job_rows.append(row)

        batch_status = self._determine_batch_status(batch_result.job_rows)
        batch_meta = self.repo.get_batch(batch_id) or {
            "id": batch_id,
            "batch_slug": batch_slug,
            "created_at": "",
            "trigger_reason": trigger_reason,
            "left_folder": str(plans[0].left_folder),
            "right_folder": str(plans[0].right_folder),
            "status": batch_status,
        }
        file_rows_dicts = [self._batch_row_to_dict(batch_slug, row) for row in batch_result.job_rows]

        try:
            batch_ai_path: str | None = None
            if self.ai_client.is_enabled():
                try:
                    batch_ai_summary = self.ai_client.generate_batch_summary(
                        batch_meta=batch_meta,
                        file_rows=file_rows_dicts,
                    )
                    if batch_ai_summary:
                        batch_ai_path = self.report_renderer.write_batch_ai_summary_file(
                            batch_slug=batch_slug,
                            summary_text=batch_ai_summary.summary_text,
                        )
                        self.repo.add_batch_report(batch_id, "batch_ai_summary_md", batch_ai_path)
                except Exception as exc:
                    if batch_status == "done":
                        batch_status = "partial_failed"
                    self.repo.update_batch_status(batch_id, batch_status, error_message=f"Batch AI summary failed: {exc}")

            if batch_ai_path:
                batch_meta = dict(batch_meta)
                batch_meta["batch_ai_summary_relpath"] = self._to_report_relpath(batch_ai_path)
            batch_summary_paths = self.report_renderer.render_batch_summary_from_rows(
                batch_slug=batch_slug,
                batch_meta=batch_meta,
                file_rows=file_rows_dicts,
            )
            if "batch_index_html" in batch_summary_paths:
                self.repo.add_batch_report(batch_id, "batch_index_html", batch_summary_paths["batch_index_html"])
            if "batch_summary_csv" in batch_summary_paths:
                self.repo.add_batch_report(batch_id, "batch_summary_csv", batch_summary_paths["batch_summary_csv"])
            self.repo.set_batch_summary_paths(
                batch_id,
                summary_html_path=batch_summary_paths.get("batch_index_html"),
                summary_csv_path=batch_summary_paths.get("batch_summary_csv"),
            )
            self.repo.update_batch_status(batch_id, batch_status)
        except Exception as exc:
            self.repo.update_batch_status(batch_id, "partial_failed", error_message=f"Batch summary generation failed: {exc}")
            # Batch summary generation failure should not discard per-file results.

        return batch_result.job_ids

    def process_planned_pair(
        self,
        plan: PlannedComparison,
        *,
        trigger_reason: str,
        launch_bc: bool = True,
        batch_id: int | None = None,
        batch_slug: str | None = None,
        file_subdir: str | None = None,
    ) -> BatchJobSummaryRow:
        job_id = self.repo.create_job(
            left_folder=str(plan.left_folder),
            right_folder=str(plan.right_folder),
            left_csv_path=str(plan.left_csv),
            right_csv_path=str(plan.right_csv),
            trigger_reason=trigger_reason,
            status="queued",
        )
        job = self.repo.get_job(job_id) or {}
        created_at = str(job.get("created_at") or "")
        if batch_id is not None and file_subdir:
            self.repo.link_job_to_batch(job_id, batch_id, file_subdir)

        try:
            self.repo.log_job(job_id, "INFO", f"Planned comparison: {plan.left_folder.name} vs {plan.right_folder.name}")
            if batch_slug and file_subdir:
                self.repo.log_job(job_id, "INFO", f"Batch {batch_slug} report dir assigned: {plan.left_csv.name} -> {file_subdir}")
            if not plan.left_csv.exists():
                raise FileNotFoundError(
                    self._build_missing_csv_message(
                        side="Left",
                        missing_path=plan.left_csv,
                        folder=plan.left_folder,
                        configured_name=self.planner.config.csv.fixed_filename,
                    )
                )
            if not plan.right_csv.exists():
                raise FileNotFoundError(
                    self._build_missing_csv_message(
                        side="Right",
                        missing_path=plan.right_csv,
                        folder=plan.right_folder,
                        configured_name=self.planner.config.csv.fixed_filename,
                    )
                )

            self.repo.update_job_status(job_id, "comparing")
            if launch_bc:
                launch_result = self.compare_tool_launcher.launch(
                    left_folder=plan.left_folder,
                    right_folder=plan.right_folder,
                    left_csv=plan.left_csv,
                    right_csv=plan.right_csv,
                )
                if launch_result.launched:
                    self.repo.log_job(
                        job_id,
                        "INFO",
                        f"{self.compare_tool_launcher.tool_display_name()} launched: {' '.join(launch_result.command)}",
                    )
                elif launch_result.command:
                    self.repo.log_job(
                        job_id,
                        "WARNING",
                        f"{self.compare_tool_launcher.tool_display_name()} not launched: {launch_result.error or 'disabled'}",
                    )
            else:
                self.repo.log_job(
                    job_id,
                    "INFO",
                    f"{self.compare_tool_launcher.tool_display_name()} launch skipped for this CSV (already launched once for folder pair).",
                )

            result = self.diff_engine.compare_files(plan.left_csv, plan.right_csv)
            self.repo.set_job_hashes(job_id, result.left_snapshot.sha256, result.right_snapshot.sha256)
            if self.repo.has_completed_job_for_hashes(result.left_snapshot.sha256, result.right_snapshot.sha256):
                # Keep generating reports for repeated manual/scan runs. We only record a log hint here.
                self.repo.log_job(job_id, "INFO", "Duplicate hash pair detected, but continuing to persist and render reports for this batch.")

            self.repo.save_diff_result(job_id, result)
            self.repo.update_job_status(job_id, "persisted")

            report_paths = self.report_renderer.render_from_result(
                job_id,
                result,
                batch_slug=batch_slug,
                file_subdir=file_subdir,
            )
            for report_type, file_path in report_paths.items():
                self.repo.add_report(job_id, report_type, file_path)
            self.repo.update_job_status(job_id, "reported")

            ai_path: str | None = None
            final_status = "done"
            if self.ai_client.is_enabled():
                try:
                    ai_summary = self.ai_client.generate_summary(result)
                    if ai_summary:
                        self.repo.save_ai_summary(job_id, ai_summary)
                        ai_path = self.report_renderer.write_ai_summary_file(
                            job_id,
                            ai_summary.summary_text,
                            batch_slug=batch_slug,
                            file_subdir=file_subdir,
                        )
                        self.repo.add_report(job_id, "ai_summary_md", ai_path)
                        self.repo.update_job_status(job_id, "ai_summarized")
                except Exception as exc:
                    self.repo.log_job(job_id, "ERROR", f"AI summary failed: {exc}")
                    self.repo.update_job_status(job_id, "reported_done_ai_failed", error_message=f"AI summary failed: {exc}")
                    final_status = "reported_done_ai_failed"

            if final_status == "done":
                self.repo.update_job_status(job_id, "done")

            return self._build_success_batch_row(
                job_id=job_id,
                created_at=created_at,
                plan=plan,
                file_subdir=file_subdir or safe_filename(plan.left_csv.stem),
                status=final_status,
                result=result,
                report_paths=report_paths,
                ai_path=ai_path,
            )
        except Exception as exc:
            self.repo.log_job(job_id, "ERROR", f"{exc}\n{traceback.format_exc()}")
            self.repo.update_job_status(job_id, "failed", error_message=str(exc))
            return BatchJobSummaryRow(
                job_id=job_id,
                file_name=plan.left_csv.name,
                file_stem_dir=file_subdir or safe_filename(plan.left_csv.stem),
                status="failed",
                left_csv_path=str(plan.left_csv),
                right_csv_path=str(plan.right_csv),
                created_at=created_at,
                error_message=str(exc),
            )

    def rebuild_reports(self, job_id: int) -> dict[str, str]:
        bundle = self.repo.fetch_job_bundle(job_id)
        batch = bundle.get("batch") or {}
        job = bundle.get("job") or {}
        batch_slug = batch.get("batch_slug")
        file_subdir = job.get("report_subdir_name")
        paths = self.report_renderer.render_from_bundle(
            job_id,
            bundle,
            batch_slug=str(batch_slug) if batch_slug else None,
            file_subdir=str(file_subdir) if file_subdir else None,
        )
        for report_type, path in paths.items():
            self.repo.add_report(job_id, report_type, path)
        ai_summary = bundle.get("ai_summary")
        if ai_summary and ai_summary.get("summary_text"):
            ai_path = self.report_renderer.write_ai_summary_file(
                job_id,
                ai_summary["summary_text"],
                batch_slug=str(batch_slug) if batch_slug else None,
                file_subdir=str(file_subdir) if file_subdir else None,
            )
            self.repo.add_report(job_id, "ai_summary_md", ai_path)
            paths["ai_summary_md"] = ai_path
        return paths

    def _build_success_batch_row(
        self,
        *,
        job_id: int,
        created_at: str,
        plan: PlannedComparison,
        file_subdir: str,
        status: str,
        result: CsvDiffResult,
        report_paths: dict[str, str],
        ai_path: str | None,
    ) -> BatchJobSummaryRow:
        return BatchJobSummaryRow(
            job_id=job_id,
            file_name=plan.left_csv.name,
            file_stem_dir=file_subdir,
            status=status,
            left_csv_path=str(plan.left_csv),
            right_csv_path=str(plan.right_csv),
            created_at=created_at,
            total_rows_left=result.summary.total_rows_left,
            total_rows_right=result.summary.total_rows_right,
            exact_match_rows=result.summary.exact_match_rows,
            added_rows=result.summary.added_rows,
            deleted_rows=result.summary.deleted_rows,
            suspected_modified_rows=result.summary.suspected_modified_rows,
            added_columns_count=len(result.schema_diff.added_columns),
            removed_columns_count=len(result.schema_diff.removed_columns),
            reordered_columns_count=len(result.schema_diff.reordered_columns),
            detailed_report_relpath=self._to_report_relpath(report_paths.get("detailed_html")),
            row_diffs_relpath=self._to_report_relpath(report_paths.get("detailed_csv")),
            ai_summary_relpath=self._to_report_relpath(ai_path),
        )

    def _build_batch_slug(self) -> str:
        return f"results-{local_now_compact_timestamp()}"

    def _create_unique_batch(self, *, trigger_reason: str, left_folder: str, right_folder: str) -> tuple[str, int]:
        # Keep strict `results-YYYYMMDDHHMMSS` format; if same-second collision happens, wait for next second.
        last_slug: str | None = None
        for _ in range(3):
            batch_slug = self._build_batch_slug()
            if batch_slug == last_slug:
                time.sleep(1.05)
                batch_slug = self._build_batch_slug()
            try:
                batch_id = self.repo.create_batch(
                    batch_slug=batch_slug,
                    trigger_reason=trigger_reason,
                    left_folder=left_folder,
                    right_folder=right_folder,
                    status="running",
                )
                return batch_slug, batch_id
            except sqlite3.IntegrityError:
                last_slug = batch_slug
                time.sleep(1.05)
        # Final attempt lets the original DB error bubble if something else is wrong.
        batch_slug = self._build_batch_slug()
        batch_id = self.repo.create_batch(
            batch_slug=batch_slug,
            trigger_reason=trigger_reason,
            left_folder=left_folder,
            right_folder=right_folder,
            status="running",
        )
        return batch_slug, batch_id

    def _allocate_file_subdir(self, csv_path: Path, used_dirs: set[str]) -> str:
        base = safe_filename(csv_path.stem)
        candidate = base
        idx = 2
        while candidate.lower() in {x.lower() for x in used_dirs}:
            candidate = f"{base}__{idx}"
            idx += 1
        used_dirs.add(candidate)
        return candidate

    def _to_report_relpath(self, path: str | None) -> str | None:
        if not path:
            return None
        p = Path(path).resolve()
        try:
            return str(p.relative_to(self.report_renderer.output_dir)).replace("\\", "/")
        except Exception:
            return str(p).replace("\\", "/")

    def _batch_row_to_dict(self, batch_slug: str, row: BatchJobSummaryRow) -> dict[str, object]:
        return {
            "batch_slug": batch_slug,
            "job_id": row.job_id,
            "file_name": row.file_name,
            "file_stem_dir": row.file_stem_dir,
            "status": row.status,
            "left_csv_path": row.left_csv_path,
            "right_csv_path": row.right_csv_path,
            "total_rows_left": row.total_rows_left,
            "total_rows_right": row.total_rows_right,
            "exact_match_rows": row.exact_match_rows,
            "added_rows": row.added_rows,
            "deleted_rows": row.deleted_rows,
            "suspected_modified_rows": row.suspected_modified_rows,
            "added_columns_count": row.added_columns_count,
            "removed_columns_count": row.removed_columns_count,
            "reordered_columns_count": row.reordered_columns_count,
            "detailed_report_relpath": row.detailed_report_relpath,
            "row_diffs_relpath": row.row_diffs_relpath,
            "ai_summary_relpath": row.ai_summary_relpath,
            "created_at": row.created_at,
            "error_message": row.error_message,
        }

    def _determine_batch_status(self, rows: list[BatchJobSummaryRow]) -> str:
        if not rows:
            return "failed"
        statuses = [row.status for row in rows]
        success_statuses = {"done", "duplicate_skipped", "reported_done_ai_failed"}
        if all(status in success_statuses for status in statuses):
            return "done"
        if any(status in success_statuses for status in statuses):
            return "partial_failed"
        return "failed"

    def _build_missing_csv_message(self, *, side: str, missing_path: Path, folder: Path, configured_name: str) -> str:
        available = self.planner.describe_csv_files(folder)
        available_text = ", ".join(available) if available else "(no csv files found)"
        hint = ""
        if available and configured_name.lower() == "result.csv":
            hint = " Hint: your folders contain multiple CSVs. Set `csv.fixed_filename` to a real filename (e.g. `DM.csv`) or a glob pattern like `*.csv`."
        return (
            f"{side} CSV missing: {missing_path}. "
            f"Configured csv.fixed_filename='{configured_name}'. "
            f"Available CSV files in {folder}: {available_text}.{hint}"
        )

    def _build_no_matching_csv_message(self, left: Path, right: Path, pattern: str) -> str:
        left_files = self.planner.describe_csv_files(left)
        right_files = self.planner.describe_csv_files(right)
        return (
            f"No matching CSV files for pattern '{pattern}'. "
            f"Left folder CSVs: {', '.join(left_files) if left_files else '(none)'}; "
            f"Right folder CSVs: {', '.join(right_files) if right_files else '(none)'}."
        )
