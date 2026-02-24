# 架构说明

本文档描述系统组件关系、数据流与主要状态流。

## 运行模式（CLI）

`medaudit_diff_watcher/cli.py` 当前支持以下子命令：

- `doctor`：环境/配置诊断
- `run`：常驻监控（线程化启动每个 watch scope）
- `scan-once`：扫描一次并处理最新目录对
- `compare`：手动指定左右目录比较
- `rebuild-report`：从数据库重建报告文件

## 组件关系（文字图）

```text
CLI (cli.py)
  -> Config Loader (config.py)
  -> [per watch scope] PipelineRunner (pipeline.py)
       -> JobPlanner (planner.py)
       -> CompareToolLauncher (compare_tool_launcher.py)
       -> CsvDiffEngine (csv_diff.py)
       -> DiffRepository (repository.py / SQLite)
       -> DetailedReportRenderer (reporting.py)
       -> AISummaryClient (ai_client.py)

WatcherService (watcher.py)
  -> detects new/stable folders
  -> triggers PipelineRunner.process_latest_pairs()
```

## 典型数据流（从目录发现到报告生成）

1. `WatcherService` 发现新子目录（通过轮询或 watchdog）
2. `FolderStabilityChecker` 等待目录稳定
3. `JobPlanner` 选择最新两个子目录（`latest_two`）
4. `JobPlanner` 根据 `csv.fixed_filename` 生成计划：
   - 固定文件名 -> 单个计划
   - 通配符（如 `*.csv`）-> 多个文件计划（交集文件名）
5. `PipelineRunner` 创建批次（`compare_batches`）并逐个创建任务（`compare_jobs`）
6. `CompareToolLauncher`（可选）拉起外部对比工具
7. `CsvDiffEngine` 比较左右 CSV，生成 `CsvDiffResult`
8. `DiffRepository` 持久化结果（快照、schema diff、summary、row/cell diffs、日志）
9. `DetailedReportRenderer` 生成文件级报告（HTML/CSV）
10. `AISummaryClient`（可选）生成文件级 AI 总结并写入 `ai_summary.md`
11. `PipelineRunner` 汇总批次行结果，生成批次 `summary.csv` / `index.html`
12. `AISummaryClient`（可选）生成批次级 AI 总结 `batch_ai_summary.md`

## 多监控（Multi-Watch）隔离策略

当配置 `watch.root_dirs`（非空列表）时：

- `config.expand_watch_scopes()` 会为每个根目录生成一个 `WatchScope`
- 每个 scope 拥有独立的 `AppConfig` 副本
- 自动分配 `watch_name`（默认取根目录最后一级名称；重复名会加 `__2`、`__3`）
- 自动隔离存储路径：
  - `db.sqlite_path` -> `data/<watch_name>/medaudit_diff.db`
  - `report.output_dir` -> `reports/<watch_name>/`

这意味着单进程可以并行监控多个目录，但数据/报告仍按域隔离。

## AI 总结生成时机

### 单文件级 AI 总结

- 在单个 CSV 的详细报告生成之后执行
- 输出文件：`ai_summary.md`
- 若 AI 调用失败：
  - 任务状态会标记为 `reported_done_ai_failed`
  - 已有报告仍保留（不回滚）

### 批次级 AI 总结

- 在本批次全部文件处理完成后执行
- 输入为批次级结构化汇总（不是简单拼接每个文件总结）
- 输出文件：`batch_ai_summary.md`
- 失败时批次仍保留文件级结果，批次状态可能变为 `partial_failed`

## 状态流（关键）

### Job 状态（`compare_jobs.status`）

常见状态：

- `queued`
- `comparing`
- `persisted`
- `reported`
- `ai_summarized`（中间状态）
- `done`
- `reported_done_ai_failed`
- `failed`

兼容保留状态（代码可识别但当前流程未主动写入）：

- `duplicate_skipped`

### Batch 状态（`compare_batches.status`）

- `running`
- `done`
- `partial_failed`
- `failed`

判断逻辑在 `PipelineRunner._determine_batch_status()` 中完成。

## 错误处理策略（实现层面）

- 单文件失败不会阻断整个批次的其他文件处理
- 批次汇总生成失败不会抹掉已生成的文件级报告
- AI 失败不影响已完成的 CSV 差异计算与报告落地
- `rebuild-report` 基于数据库内容重建，不重新执行 CSV 比较或外部 compare tool

