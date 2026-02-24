from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from medaudit_diff_watcher.config import AIConfig
from medaudit_diff_watcher.models import AISummaryResult, CsvDiffResult
from medaudit_diff_watcher.utils import json_dumps


class AISummaryClient:
    PROMPT_VERSION = "v3"
    BATCH_PROMPT_VERSION = "batch_v1"

    def __init__(self, config: AIConfig) -> None:
        self.config = config

    def is_enabled(self) -> bool:
        return bool(self.config.enabled and self.config.base_url and self.config.api_key and self.config.model)

    def generate_summary(self, result: CsvDiffResult) -> AISummaryResult | None:
        if not self.is_enabled():
            return None
        if self._is_identical_result(result):
            return AISummaryResult(
                summary_text=self._build_identical_summary(result),
                model="local-template-identical",
                prompt_version=self.PROMPT_VERSION,
                token_usage_json=json_dumps({}),
            )

        payload = result.to_ai_payload(include_raw_rows=self.config.send_raw_rows)
        prompt = self._build_prompt(payload)
        return self._request_chat_summary(prompt=prompt, prompt_version=self.PROMPT_VERSION)

    def generate_batch_summary(
        self,
        *,
        batch_meta: dict[str, Any],
        file_rows: list[dict[str, Any]],
    ) -> AISummaryResult | None:
        if not self.is_enabled():
            return None
        if self._is_identical_batch(file_rows):
            return AISummaryResult(
                summary_text=self._build_identical_batch_summary(batch_meta, file_rows),
                model="local-template-batch-identical",
                prompt_version=self.BATCH_PROMPT_VERSION,
                token_usage_json=json_dumps({}),
            )

        payload = self._build_batch_payload(batch_meta=batch_meta, file_rows=file_rows)
        prompt = self._build_batch_prompt(payload)
        return self._request_chat_summary(prompt=prompt, prompt_version=self.BATCH_PROMPT_VERSION)

    def _build_prompt(self, payload: dict[str, Any]) -> str:
        return (
            "请基于以下结构化差异数据，输出一份中文总结（准确、便于人工复核）。"
            "请忽略 confidence 指标对结论的影响，不要用 confidence 评估风险等级。"
            "若需要提到启发式匹配，只说明“疑似修改行来自启发式匹配，非严格主键对齐”。"
            "请优先使用 field_change_patterns 中的统计，明确写出“字段名 + 旧值 -> 新值 + 影响行数”。"
            "例如：AGEU: YEARS -> YEAR（200行）。\n"
            "输出请使用以下结构：\n"
            "1. 总体变化\n"
            "2. 结构变化（列新增/删除/顺序变化）\n"
            "3. 具体字段变化（逐字段列出主要值变化及行数）\n"
            "4. 风险提示与建议复核点\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _build_batch_prompt(self, payload: dict[str, Any]) -> str:
        return (
            "请基于以下批次级结构化汇总数据，输出一份中文总总结（用于先看总览再逐文件核查）。"
            "要求：\n"
            "1. 先给出本批次整体结论（涉及文件数、异常文件数、主要变化类型）\n"
            "2. 按文件列出重点变化（优先按疑似修改行/新增删除行多的文件）\n"
            "3. 若某些文件无差异，请归并描述，不要逐个重复长篇描述\n"
            "4. 不要捏造数字，只使用提供的统计\n"
            "5. 若提到疑似修改，请说明其来自启发式匹配（非严格主键对齐）\n"
            "6. 输出结构：总体结论 / 重点文件变化 / 无差异文件 / 风险提示与建议复核点\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

    def _is_identical_result(self, result: CsvDiffResult) -> bool:
        schema = result.schema_diff
        summary = result.summary
        return (
            not schema.added_columns
            and not schema.removed_columns
            and not schema.reordered_columns
            and summary.total_rows_left == summary.total_rows_right
            and summary.exact_match_rows == summary.total_rows_left
            and summary.added_rows == 0
            and summary.deleted_rows == 0
            and summary.suspected_modified_rows == 0
        )

    def _build_identical_summary(self, result: CsvDiffResult) -> str:
        left_name = Path(result.left_snapshot.path).name or result.left_snapshot.path
        right_name = Path(result.right_snapshot.path).name or result.right_snapshot.path
        total_rows = result.summary.total_rows_left

        lines = [
            "# AI比较总结（固定模板）",
            "",
            "1. 总体变化",
            f"- 本次比较结果：两个CSV在本工具比对口径下无差异（内容一致）。",
            f"- 左侧文件：`{left_name}`；右侧文件：`{right_name}`。",
            f"- 行数统计：左侧 {total_rows} 行，右侧 {result.summary.total_rows_right} 行，完全匹配 {result.summary.exact_match_rows} 行。",
            "",
            "2. 结构变化（列新增/删除/顺序变化）",
            "- 未发现结构变化（无新增列、无删除列、无列顺序变化）。",
            "",
            "3. 具体字段变化",
            "- 未发现字段值变化。",
            "",
            "4. 风险提示与建议复核点",
            "- 当前结果显示两份CSV一致，可按需要抽查表头、行数和来源批次。",
            "- 若业务上预期应有变化，请核对是否比较到了正确的两个子文件夹/CSV文件。",
        ]
        if result.warnings:
            lines.extend(["- 备注（工具告警，不代表数据差异）："])
            lines.extend([f"  - {warning}" for warning in result.warnings])
        return "\n".join(lines).strip() + "\n"

    def _is_identical_batch(self, file_rows: list[dict[str, Any]]) -> bool:
        if not file_rows:
            return False
        success_statuses = {"done", "reported_done_ai_failed"}
        for row in file_rows:
            if str(row.get("status") or "") not in success_statuses:
                return False
            if int(row.get("added_rows") or 0) != 0:
                return False
            if int(row.get("deleted_rows") or 0) != 0:
                return False
            if int(row.get("suspected_modified_rows") or 0) != 0:
                return False
            if int(row.get("added_columns_count") or 0) != 0:
                return False
            if int(row.get("removed_columns_count") or 0) != 0:
                return False
            if int(row.get("reordered_columns_count") or 0) != 0:
                return False
            total_left = row.get("total_rows_left")
            total_right = row.get("total_rows_right")
            exact = row.get("exact_match_rows")
            if total_left is None or total_right is None or exact is None:
                return False
            if int(total_left) != int(total_right):
                return False
            if int(exact) != int(total_left):
                return False
        return True

    def _build_identical_batch_summary(self, batch_meta: dict[str, Any], file_rows: list[dict[str, Any]]) -> str:
        file_names = [str(r.get("file_name") or "") for r in file_rows]
        file_names_sorted = sorted([name for name in file_names if name], key=str.lower)
        sample_names = ", ".join(file_names_sorted[:10]) if file_names_sorted else "(none)"
        more_count = max(len(file_names_sorted) - 10, 0)
        lines = [
            "# 批次AI总结（固定模板）",
            "",
            "## 总体结论",
            f"- 批次 `{batch_meta.get('batch_slug', '')}` 本次共比较 {len(file_rows)} 个文件，结果均为无差异（在本工具比对口径下内容一致）。",
            "- 未发现结构变化（列新增/删除/顺序变化）以及数据行变化（新增/删除/疑似修改）。",
            "",
            "## 无差异文件",
            f"- {sample_names}{' 等' if more_count > 0 else ''}",
        ]
        if more_count > 0:
            lines.append(f"- 其余无差异文件数：{more_count}")
        lines.extend(
            [
                "",
                "## 风险提示与建议复核点",
                "- 可抽查批次来源目录、文件名映射与行数，确认比较对象正确。",
                "- 若业务预期本次应有更新，请重点核对是否选择了正确的两个子文件夹版本。",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def _build_batch_payload(self, *, batch_meta: dict[str, Any], file_rows: list[dict[str, Any]]) -> dict[str, Any]:
        success_rows = [r for r in file_rows if str(r.get("status") or "") in {"done", "reported_done_ai_failed"}]
        failed_rows = [r for r in file_rows if str(r.get("status") or "") == "failed"]
        sum_added = sum(int(r.get("added_rows") or 0) for r in success_rows)
        sum_deleted = sum(int(r.get("deleted_rows") or 0) for r in success_rows)
        sum_suspected = sum(int(r.get("suspected_modified_rows") or 0) for r in success_rows)
        sum_added_cols = sum(int(r.get("added_columns_count") or 0) for r in success_rows)
        sum_removed_cols = sum(int(r.get("removed_columns_count") or 0) for r in success_rows)
        sum_reordered_cols = sum(int(r.get("reordered_columns_count") or 0) for r in success_rows)

        file_items: list[dict[str, Any]] = []
        for row in file_rows:
            file_items.append(
                {
                    "file_name": row.get("file_name"),
                    "status": row.get("status"),
                    "rows": {
                        "left": row.get("total_rows_left"),
                        "right": row.get("total_rows_right"),
                        "exact_match": row.get("exact_match_rows"),
                        "added": row.get("added_rows"),
                        "deleted": row.get("deleted_rows"),
                        "suspected_modified": row.get("suspected_modified_rows"),
                    },
                    "schema_changes": {
                        "added_columns_count": row.get("added_columns_count"),
                        "removed_columns_count": row.get("removed_columns_count"),
                        "reordered_columns_count": row.get("reordered_columns_count"),
                    },
                    "links": {
                        "detail": row.get("detailed_report_relpath"),
                        "file_ai_summary": row.get("ai_summary_relpath"),
                    },
                    "error_message": row.get("error_message"),
                }
            )

        def _severity_key(item: dict[str, Any]) -> tuple[int, int, int, str]:
            rows = item.get("rows") or {}
            schema_changes = item.get("schema_changes") or {}
            score = (
                int(rows.get("suspected_modified") or 0)
                + int(rows.get("added") or 0)
                + int(rows.get("deleted") or 0)
                + int(schema_changes.get("added_columns_count") or 0)
                + int(schema_changes.get("removed_columns_count") or 0)
                + int(schema_changes.get("reordered_columns_count") or 0)
            )
            return (
                score,
                int(rows.get("suspected_modified") or 0),
                int(rows.get("added") or 0) + int(rows.get("deleted") or 0),
                str(item.get("file_name") or ""),
            )

        top_changed_files = sorted(file_items, key=_severity_key, reverse=True)[:10]
        no_diff_files = sorted(
            [
                str(r.get("file_name") or "")
                for r in success_rows
                if int(r.get("added_rows") or 0) == 0
                and int(r.get("deleted_rows") or 0) == 0
                and int(r.get("suspected_modified_rows") or 0) == 0
                and int(r.get("added_columns_count") or 0) == 0
                and int(r.get("removed_columns_count") or 0) == 0
                and int(r.get("reordered_columns_count") or 0) == 0
            ],
            key=str.lower,
        )

        return {
            "batch_meta": {
                "batch_slug": batch_meta.get("batch_slug"),
                "trigger_reason": batch_meta.get("trigger_reason"),
                "created_at": batch_meta.get("created_at"),
                "left_folder": batch_meta.get("left_folder"),
                "right_folder": batch_meta.get("right_folder"),
                "status": batch_meta.get("status"),
            },
            "batch_totals": {
                "total_files": len(file_rows),
                "success_files": len(success_rows),
                "failed_files": len(failed_rows),
                "sum_added_rows": sum_added,
                "sum_deleted_rows": sum_deleted,
                "sum_suspected_modified_rows": sum_suspected,
                "sum_added_columns_count": sum_added_cols,
                "sum_removed_columns_count": sum_removed_cols,
                "sum_reordered_columns_count": sum_reordered_cols,
            },
            "top_changed_files": top_changed_files,
            "no_diff_file_names": no_diff_files[:50],
            "failed_files": [
                {
                    "file_name": r.get("file_name"),
                    "status": r.get("status"),
                    "error_message": r.get("error_message"),
                }
                for r in failed_rows
            ],
            "all_file_rows": file_items,
        }

    def _request_chat_summary(self, *, prompt: str, prompt_version: str) -> AISummaryResult | None:
        body = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a medical audit diff summarizer. "
                        "Summarize differences based only on provided structured stats. "
                        "Do not invent counts. Use concise bullet points and note uncertainty for heuristic matches."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }

        url = self.config.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        last_error: str | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                resp = self._post_json(url, body, headers=headers, timeout=self.config.timeout_sec)
                text = self._extract_text(resp)
                usage = resp.get("usage", {})
                return AISummaryResult(
                    summary_text=text,
                    model=str(resp.get("model") or self.config.model),
                    prompt_version=prompt_version,
                    token_usage_json=json_dumps(usage),
                )
            except Exception as exc:  # pragma: no cover - network-dependent
                last_error = str(exc)
                if attempt < self.config.max_retries:
                    time.sleep(min(2**attempt, 5))
        if last_error:
            raise RuntimeError(f"AI summary request failed: {last_error}")
        return None

    def _post_json(
        self,
        url: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str],
        timeout: int,
    ) -> dict[str, Any]:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        return json.loads(data.decode("utf-8"))

    def _extract_text(self, resp: dict[str, Any]) -> str:
        choices = resp.get("choices") or []
        if not choices:
            raise RuntimeError("No choices returned by AI API")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("AI API response missing string message.content")
        return content.strip()
