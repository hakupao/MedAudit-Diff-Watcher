# 报告与存储说明

本文档说明报告目录布局、文件含义与 SQLite 存储结构（按用途分组）。

字段级表结构、索引、迁移与 SQL 查询示例请见 `doc/DATABASE.md`。

## 报告输出目录布局（批次模式）

新版本主要按“批次”组织报告，批次目录名格式：

```text
results-YYYYMMDDHHMMSS
```

示例：

```text
reports/
  results-20260224143010/
    index.html
    summary.csv
    batch_ai_summary.md      # 启用 AI 且批次总结成功时生成
    DM/
      detailed_report.html
      row_diffs.csv
      ai_summary.md          # 启用 AI 且该文件总结成功时生成
    CM/
      detailed_report.html
      row_diffs.csv
```

说明：

- `<csv_stem>/` 由 CSV 文件名 stem 生成（必要时会自动加后缀避免冲突，如 `DM__2`）
- `summary.csv` 是批次内所有文件任务的汇总表
- `index.html` 是批次总览页面（带详情链接）

## 历史兼容布局（`job_<id>`）

当执行历史任务重建、或缺少批次信息时，仍可能出现旧式路径：

```text
reports/
  job_123/
    detailed_report.html
    row_diffs.csv
    ai_summary.md
```

这是兼容行为，不代表当前批次模式失效。

## 多监控模式下的目录隔离

当使用 `watch.root_dirs` 时，系统会自动隔离每个 watch scope 的数据与报告：

```text
reports/
  <watch_name_A>/
    results-YYYYMMDDHHMMSS/
      ...
  <watch_name_B>/
    results-YYYYMMDDHHMMSS/
      ...

data/
  <watch_name_A>/medaudit_diff.db
  <watch_name_B>/medaudit_diff.db
```

`watch_name` 默认来自监控根目录最后一级名称；重复名称会自动加 `__2`、`__3`。

## 报告文件说明

### 批次级

- `index.html`
  - 批次总体统计（完成/失败/AI失败但已报告等）
  - 文件级结果列表与链接

- `summary.csv`
  - 文件级任务汇总表（机器可读）
  - 包含行数/差异计数/报告相对路径/错误信息等字段

- `batch_ai_summary.md`
  - 批次级 AI 中文总结（可选）

### 文件级

- `detailed_report.html`
  - 单文件详细摘要、结构差异、疑似修改展示（截断展示）
  - 若某个 CSV 只存在于一侧，报告会把另一侧视为“空文件”，展示整文件新增或删除

- `row_diffs.csv`
  - 行级与单元格级差异导出（适合进一步筛查）

- `ai_summary.md`
  - 单文件 AI 总结（可选）

## `row_diffs.csv` 内容概览

当前实现会写出类似字段：

- `row_type`
- `match_group_id`
- `confidence`
- `column_name`
- `left_value`
- `right_value`
- `row_json`

常见 `row_type`：

- `added`
- `deleted`
- `suspected_modified`
- `cell_diff`

## SQLite 存储（按用途分组）

SQLite 在 `DiffRepository` 初始化时创建，并启用 `WAL` 模式。

### 任务/批次编排

- `compare_batches`
  - 批次元数据与状态
  - 批次汇总报告路径

- `compare_jobs`
  - 文件级任务元数据、状态、左右路径、哈希、所属批次、报告子目录名

- `job_logs`
  - 任务级日志（INFO/WARNING/ERROR）

### 差异结果数据

- `file_snapshots`
  - 左右文件快照（大小、mtime、sha256、编码、分隔符）

- `schema_diffs`
  - 表头与结构差异（新增/删除/重排）

- `diff_summaries`
  - 行级汇总计数（added/deleted/suspected/exact）

- `row_diffs`
  - 行级差异（含疑似修改行左右 row json）

- `cell_diffs`
  - 疑似修改行对应的单元格差异明细

### 报告与 AI 结果

- `reports`
  - 文件级报告路径登记

- `batch_reports`
  - 批次级报告路径登记

- `ai_summaries`
  - 文件级 AI 总结文本、模型、prompt_version、token_usage

## `rebuild-report` 的适用场景与限制

### 适用场景

- 报告文件被误删，但 SQLite 仍在
- 想重建 HTML/CSV 报告用于复核
- 历史任务需要重新导出到当前报告目录

### 限制与注意事项

- 不会重新执行 CSV 比较
- 不会重新调用 compare tool（Beyond Compare/WinMerge）
- 仅在数据库中存在 `ai_summaries` 记录时，才会重写 `ai_summary.md`
- 若数据库缺少对应 `job_id`，命令会报错
- 多监控场景建议显式传 `--watch-name`

## 兼容性说明

- `compare_jobs` 的历史 schema 字段缺失会在仓库初始化时做轻量补列兼容（见 `repository.py`）
- 报告路径兼容批次模式与旧 `job_<id>` 模式
