from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any

from medaudit_diff_watcher.models import CsvDiffResult


class DetailedReportRenderer:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_from_result(
        self,
        job_id: int,
        result: CsvDiffResult,
        *,
        batch_slug: str | None = None,
        file_subdir: str | None = None,
    ) -> dict[str, str]:
        job_dir = self._resolve_job_dir(job_id, batch_slug=batch_slug, file_subdir=file_subdir)
        html_path = job_dir / "detailed_report.html"
        csv_path = job_dir / "row_diffs.csv"

        html_path.write_text(self._build_html(job_id, result), encoding="utf-8")
        self._write_row_diff_csv(csv_path, result)
        return {"detailed_html": str(html_path), "detailed_csv": str(csv_path)}

    def render_from_bundle(
        self,
        job_id: int,
        bundle: dict[str, Any],
        *,
        batch_slug: str | None = None,
        file_subdir: str | None = None,
    ) -> dict[str, str]:
        job_dir = self._resolve_job_dir(job_id, batch_slug=batch_slug, file_subdir=file_subdir)
        html_path = job_dir / "detailed_report.html"
        csv_path = job_dir / "row_diffs.csv"
        html_path.write_text(self._build_html_from_bundle(job_id, bundle), encoding="utf-8")
        self._write_row_diff_csv_from_bundle(csv_path, bundle)
        return {"detailed_html": str(html_path), "detailed_csv": str(csv_path)}

    def write_ai_summary_file(
        self,
        job_id: int,
        summary_text: str,
        *,
        batch_slug: str | None = None,
        file_subdir: str | None = None,
    ) -> str:
        job_dir = self._resolve_job_dir(job_id, batch_slug=batch_slug, file_subdir=file_subdir)
        path = job_dir / "ai_summary.md"
        path.write_text(summary_text, encoding="utf-8")
        return str(path)

    def write_batch_ai_summary_file(self, *, batch_slug: str, summary_text: str) -> str:
        batch_dir = self.output_dir / batch_slug
        batch_dir.mkdir(parents=True, exist_ok=True)
        path = batch_dir / "batch_ai_summary.md"
        path.write_text(summary_text, encoding="utf-8")
        return str(path)

    def render_batch_summary_from_rows(
        self,
        *,
        batch_slug: str,
        batch_meta: dict[str, Any],
        file_rows: list[dict[str, Any]],
    ) -> dict[str, str]:
        batch_dir = self.output_dir / batch_slug
        batch_dir.mkdir(parents=True, exist_ok=True)
        csv_path = batch_dir / "summary.csv"
        html_path = batch_dir / "index.html"

        self._write_batch_summary_csv(csv_path, batch_slug=batch_slug, file_rows=file_rows)
        html_path.write_text(
            self._build_batch_summary_html(batch_slug=batch_slug, batch_meta=batch_meta, file_rows=file_rows),
            encoding="utf-8",
        )
        return {"batch_summary_csv": str(csv_path), "batch_index_html": str(html_path)}

    def _resolve_job_dir(
        self,
        job_id: int,
        *,
        batch_slug: str | None,
        file_subdir: str | None,
    ) -> Path:
        if batch_slug and file_subdir:
            path = self.output_dir / batch_slug / file_subdir
        else:
            path = self.output_dir / f"job_{job_id}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _rel_to_output(self, path: str | Path) -> str:
        p = Path(path).resolve()
        try:
            return str(p.relative_to(self.output_dir)).replace("\\", "/")
        except Exception:
            return str(p).replace("\\", "/")

    def _write_batch_summary_csv(self, path: Path, *, batch_slug: str, file_rows: list[dict[str, Any]]) -> None:
        columns = [
            "batch_slug",
            "job_id",
            "file_name",
            "file_stem_dir",
            "status",
            "left_csv_path",
            "right_csv_path",
            "total_rows_left",
            "total_rows_right",
            "exact_match_rows",
            "added_rows",
            "deleted_rows",
            "suspected_modified_rows",
            "added_columns_count",
            "removed_columns_count",
            "reordered_columns_count",
            "detailed_report_relpath",
            "row_diffs_relpath",
            "ai_summary_relpath",
            "created_at",
            "error_message",
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns)
            writer.writeheader()
            for row in file_rows:
                csv_row = {k: row.get(k, "") for k in columns}
                csv_row["batch_slug"] = batch_slug
                writer.writerow(csv_row)

    def _build_batch_summary_html(self, *, batch_slug: str, batch_meta: dict[str, Any], file_rows: list[dict[str, Any]]) -> str:
        total_files = len(file_rows)
        status_counts = {"done": 0, "failed": 0, "duplicate_skipped": 0, "reported_done_ai_failed": 0, "other": 0}
        sum_added = sum_deleted = sum_suspected = 0
        for row in file_rows:
            status = str(row.get("status") or "")
            if status in status_counts:
                status_counts[status] += 1
            else:
                status_counts["other"] += 1
            if status in {"done", "reported_done_ai_failed"}:
                sum_added += int(row.get("added_rows") or 0)
                sum_deleted += int(row.get("deleted_rows") or 0)
                sum_suspected += int(row.get("suspected_modified_rows") or 0)

        rows_html = []
        for row in file_rows:
            detail_link = row.get("detailed_report_relpath") or ""
            ai_link = row.get("ai_summary_relpath") or ""
            detail_cell = (
                f"<a href='{html.escape(detail_link)}'>详细报告</a>" if detail_link else "<span class='muted'>-</span>"
            )
            ai_cell = f"<a href='{html.escape(ai_link)}'>AI总结</a>" if ai_link else "<span class='muted'>-</span>"
            rows_html.append(
                "<tr>"
                f"<td>{html.escape(str(row.get('file_name') or ''))}</td>"
                f"<td>{html.escape(str(row.get('file_stem_dir') or ''))}</td>"
                f"<td>{html.escape(str(row.get('status') or ''))}</td>"
                f"<td>{row.get('exact_match_rows') if row.get('exact_match_rows') is not None else ''}</td>"
                f"<td>{row.get('added_rows') if row.get('added_rows') is not None else ''}</td>"
                f"<td>{row.get('deleted_rows') if row.get('deleted_rows') is not None else ''}</td>"
                f"<td>{row.get('suspected_modified_rows') if row.get('suspected_modified_rows') is not None else ''}</td>"
                f"<td>{detail_cell}</td>"
                f"<td>{ai_cell}</td>"
                "</tr>"
            )
        if not rows_html:
            rows_html.append("<tr><td colspan='9'>No file results.</td></tr>")

        batch_title = batch_meta.get("batch_slug", batch_slug)
        left_folder = str(batch_meta.get("left_folder") or "")
        right_folder = str(batch_meta.get("right_folder") or "")
        trigger_reason = str(batch_meta.get("trigger_reason") or "")
        created_at = str(batch_meta.get("created_at") or "")
        batch_ai_summary_relpath = str(batch_meta.get("batch_ai_summary_relpath") or "")
        batch_ai_summary_link = (
            f"<p><a href='{html.escape(batch_ai_summary_relpath)}'>查看批次AI总结</a></p>"
            if batch_ai_summary_relpath
            else ""
        )

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>MedAudit Batch Summary - {html.escape(batch_title)}</title>
  <style>
    body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 24px; background: #f8fafc; color: #0f172a; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .muted {{ color: #475569; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 20px; }}
    .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 8px; text-align: left; }}
    th {{ background: #f1f5f9; }}
  </style>
</head>
<body>
  <h1>批次总览: {html.escape(batch_title)}</h1>
  <p class="muted">触发原因: {html.escape(trigger_reason)}<br>创建时间(UTC): {html.escape(created_at)}<br>左目录: {html.escape(left_folder)}<br>右目录: {html.escape(right_folder)}</p>
  {batch_ai_summary_link}

  <h2>汇总统计</h2>
  <div class="grid">
    <div class="card"><strong>文件数</strong><div>{total_files}</div></div>
    <div class="card"><strong>完成</strong><div>{status_counts['done']}</div></div>
    <div class="card"><strong>AI失败但已报告</strong><div>{status_counts['reported_done_ai_failed']}</div></div>
    <div class="card"><strong>失败</strong><div>{status_counts['failed']}</div></div>
    <div class="card"><strong>重复跳过</strong><div>{status_counts['duplicate_skipped']}</div></div>
    <div class="card"><strong>合计新增行</strong><div>{sum_added}</div></div>
    <div class="card"><strong>合计删除行</strong><div>{sum_deleted}</div></div>
    <div class="card"><strong>合计疑似修改行</strong><div>{sum_suspected}</div></div>
  </div>

  <h2>文件结果</h2>
  <table>
    <thead>
      <tr>
        <th>文件名</th><th>目录名</th><th>状态</th><th>完全匹配</th><th>新增</th><th>删除</th><th>疑似修改</th><th>详细</th><th>AI总结</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</body>
</html>"""

    def _write_row_diff_csv(self, path: Path, result: CsvDiffResult) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["row_type", "match_group_id", "confidence", "column_name", "left_value", "right_value", "row_json"])
            for row in result.added_rows:
                writer.writerow(["added", "", "", "", "", "", json.dumps(row, ensure_ascii=False)])
            for row in result.deleted_rows:
                writer.writerow(["deleted", "", "", "", "", "", json.dumps(row, ensure_ascii=False)])
            for row in result.suspected_modified_rows:
                writer.writerow(
                    [
                        "suspected_modified",
                        row.match_group_id,
                        row.confidence,
                        "",
                        "",
                        "",
                        json.dumps({"left_row": row.left_row, "right_row": row.right_row}, ensure_ascii=False),
                    ]
                )
                for cell in row.cell_diffs:
                    writer.writerow(
                        [
                            "cell_diff",
                            row.match_group_id,
                            row.confidence,
                            cell.column_name,
                            cell.left_value,
                            cell.right_value,
                            "",
                        ]
                    )

    def _write_row_diff_csv_from_bundle(self, path: Path, bundle: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["row_type", "match_group_id", "confidence", "column_name", "left_value", "right_value", "row_json"])
            cell_diffs_by_match: dict[str, list[dict[str, Any]]] = {}
            for cell in bundle.get("cell_diffs", []):
                cell_diffs_by_match.setdefault(cell["match_group_id"], []).append(cell)
            for row in bundle.get("row_diffs", []):
                writer.writerow(
                    [
                        row["row_type"],
                        row.get("match_group_id") or "",
                        row.get("confidence") or "",
                        "",
                        "",
                        "",
                        json.dumps(
                            {
                                "row_json": self._maybe_json(row.get("row_json")),
                                "peer_row_json": self._maybe_json(row.get("peer_row_json")),
                            },
                            ensure_ascii=False,
                        ),
                    ]
                )
                if row.get("row_type") == "suspected_modified" and row.get("match_group_id"):
                    for cell in cell_diffs_by_match.get(row["match_group_id"], []):
                        writer.writerow(
                            [
                                "cell_diff",
                                row["match_group_id"],
                                cell.get("confidence") or "",
                                cell["column_name"],
                                cell.get("left_value") or "",
                                cell.get("right_value") or "",
                                "",
                            ]
                        )

    def _build_html(self, job_id: int, result: CsvDiffResult) -> str:
        schema = result.schema_diff
        summary = result.summary
        warning_items = "".join(f"<li>{html.escape(w)}</li>" for w in result.warnings) or "<li>None</li>"
        suspected_rows_html = "".join(
            self._suspected_row_html(row.match_group_id, row.confidence, row.cell_diffs)
            for row in result.suspected_modified_rows[:50]
        ) or "<tr><td colspan='3'>No suspected modified rows</td></tr>"

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>MedAudit Diff Report - Job {job_id}</title>
  <style>
    body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 24px; background: #f8fafc; color: #0f172a; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 20px; }}
    .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f1f5f9; }}
    code {{ background: #e2e8f0; padding: 1px 4px; border-radius: 4px; }}
    .muted {{ color: #475569; }}
  </style>
</head>
<body>
  <h1>详细比较报告 (Job {job_id})</h1>
  <p class="muted">左侧文件: <code>{html.escape(result.left_snapshot.path)}</code><br>右侧文件: <code>{html.escape(result.right_snapshot.path)}</code></p>

  <h2>摘要</h2>
  <div class="grid">
    <div class="card"><strong>左侧行数</strong><div>{summary.total_rows_left}</div></div>
    <div class="card"><strong>右侧行数</strong><div>{summary.total_rows_right}</div></div>
    <div class="card"><strong>完全匹配行</strong><div>{summary.exact_match_rows}</div></div>
    <div class="card"><strong>新增行</strong><div>{summary.added_rows}</div></div>
    <div class="card"><strong>删除行</strong><div>{summary.deleted_rows}</div></div>
    <div class="card"><strong>疑似修改行</strong><div>{summary.suspected_modified_rows}</div></div>
  </div>

  <h2>结构差异</h2>
  <div class="card">
    <div>左侧列数: {len(schema.left_headers)} / 右侧列数: {len(schema.right_headers)}</div>
    <div>新增列: {html.escape(", ".join(schema.added_columns) or "None")}</div>
    <div>删除列: {html.escape(", ".join(schema.removed_columns) or "None")}</div>
    <div>重排序列: {html.escape(", ".join(schema.reordered_columns) or "None")}</div>
  </div>

  <h2>读取信息</h2>
  <div class="card">
    <div>左侧编码/分隔符: <code>{html.escape(result.left_snapshot.encoding)}</code> / <code>{html.escape(result.left_snapshot.delimiter)}</code></div>
    <div>右侧编码/分隔符: <code>{html.escape(result.right_snapshot.encoding)}</code> / <code>{html.escape(result.right_snapshot.delimiter)}</code></div>
  </div>

  <h2>警告</h2>
  <div class="card"><ul>{warning_items}</ul></div>

  <h2>疑似修改（最多展示 50 条）</h2>
  <table>
    <thead><tr><th>Match Group</th><th>Confidence</th><th>Changed Cells</th></tr></thead>
    <tbody>{suspected_rows_html}</tbody>
  </table>
</body>
</html>"""

    def _build_html_from_bundle(self, job_id: int, bundle: dict[str, Any]) -> str:
        job = bundle["job"]
        summary = bundle.get("summary") or {}
        schema = bundle.get("schema_diff") or {}
        warnings = self._maybe_json(summary.get("warnings")) or []
        cell_diffs_by_match: dict[str, list[dict[str, Any]]] = {}
        for cell in bundle.get("cell_diffs", []):
            cell_diffs_by_match.setdefault(cell["match_group_id"], []).append(cell)

        suspected_rows_html = []
        for row in bundle.get("row_diffs", []):
            if row.get("row_type") != "suspected_modified":
                continue
            cells = cell_diffs_by_match.get(row.get("match_group_id") or "", [])
            suspected_rows_html.append(
                self._suspected_row_html_db(row.get("match_group_id") or "", row.get("confidence") or 0.0, cells)
            )
        suspected_rows_rendered = "".join(suspected_rows_html[:50]) or "<tr><td colspan='3'>No suspected modified rows</td></tr>"
        warning_items = "".join(f"<li>{html.escape(str(w))}</li>" for w in warnings) or "<li>None</li>"
        added_cols = self._maybe_json(schema.get("added_columns")) or []
        removed_cols = self._maybe_json(schema.get("removed_columns")) or []
        reordered_cols = self._maybe_json(schema.get("reordered_columns")) or []
        left_headers = self._maybe_json(schema.get("left_headers")) or []
        right_headers = self._maybe_json(schema.get("right_headers")) or []
        snapshots = {s["side"]: s for s in bundle.get("file_snapshots", [])}
        left_snap = snapshots.get("left", {})
        right_snap = snapshots.get("right", {})

        return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8" /><title>MedAudit Diff Report - Job {job_id}</title></head>
<body>
  <h1>详细比较报告 (Job {job_id})</h1>
  <p>左侧文件: {html.escape(job.get("left_csv_path", ""))}<br>右侧文件: {html.escape(job.get("right_csv_path", ""))}</p>
  <h2>摘要</h2>
  <ul>
    <li>左侧行数: {summary.get("total_rows_left", 0)}</li>
    <li>右侧行数: {summary.get("total_rows_right", 0)}</li>
    <li>完全匹配行: {summary.get("exact_match_rows", 0)}</li>
    <li>新增行: {summary.get("added_rows", 0)}</li>
    <li>删除行: {summary.get("deleted_rows", 0)}</li>
    <li>疑似修改行: {summary.get("suspected_modified_rows", 0)}</li>
  </ul>
  <h2>结构差异</h2>
  <ul>
    <li>左侧列数: {len(left_headers)}</li>
    <li>右侧列数: {len(right_headers)}</li>
    <li>新增列: {html.escape(', '.join(added_cols) or 'None')}</li>
    <li>删除列: {html.escape(', '.join(removed_cols) or 'None')}</li>
    <li>重排序列: {html.escape(', '.join(reordered_cols) or 'None')}</li>
  </ul>
  <h2>读取信息</h2>
  <ul>
    <li>左侧编码/分隔符: {html.escape(str(left_snap.get('encoding', '')))} / {html.escape(str(left_snap.get('delimiter', '')))}</li>
    <li>右侧编码/分隔符: {html.escape(str(right_snap.get('encoding', '')))} / {html.escape(str(right_snap.get('delimiter', '')))}</li>
  </ul>
  <h2>警告</h2>
  <ul>{warning_items}</ul>
  <h2>疑似修改（最多展示 50 条）</h2>
  <table border="1" cellpadding="4" cellspacing="0">
    <thead><tr><th>Match Group</th><th>Confidence</th><th>Changed Cells</th></tr></thead>
    <tbody>{suspected_rows_rendered}</tbody>
  </table>
</body>
</html>"""

    def _suspected_row_html(self, match_group_id: str, confidence: float, cells: list[Any]) -> str:
        cell_lines = "<br>".join(
            html.escape(f"{c.column_name}: '{c.left_value}' -> '{c.right_value}'") for c in cells[:20]
        )
        if len(cells) > 20:
            cell_lines += "<br>..."
        return f"<tr><td>{html.escape(match_group_id)}</td><td>{confidence}</td><td>{cell_lines}</td></tr>"

    def _suspected_row_html_db(self, match_group_id: str, confidence: float, cells: list[dict[str, Any]]) -> str:
        cell_lines = "<br>".join(
            html.escape(f"{c.get('column_name')}: '{c.get('left_value')}' -> '{c.get('right_value')}'") for c in cells[:20]
        )
        if len(cells) > 20:
            cell_lines += "<br>..."
        return f"<tr><td>{html.escape(match_group_id)}</td><td>{confidence}</td><td>{cell_lines}</td></tr>"

    def _maybe_json(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (list, dict)):
            return value
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except Exception:
            return value
