# 数据库说明（SQLite / `DiffRepository`）

本文档补充 `doc/REPORTS_AND_STORAGE.md` 中“SQLite 存储”的细节，聚焦：

- 数据库如何创建（构造）
- 表结构与字段用途
- 索引与兼容迁移
- 常见使用方式（查询/排查）

如果你只关心报告目录和文件用途，先看 `doc/REPORTS_AND_STORAGE.md`。

## 1. 数据库构造（如何创建）

## 1.1 创建时机

数据库由 `medaudit_diff_watcher/repository.py` 中的 `DiffRepository` 自动创建。

- `DiffRepository.__init__(sqlite_path)` 会：
  1. 规范化数据库路径（`Path(...).resolve()`）
  2. 创建父目录（`mkdir(parents=True, exist_ok=True)`）
  3. 调用 `_init_db()` 初始化数据库结构

这意味着：

- 不需要手工执行 SQL 建库脚本
- 首次运行 `doctor` / `run` / `scan-once` / `compare` 时，只要代码实例化了 `DiffRepository`，数据库就会被创建

## 1.2 路径来源

数据库路径来自配置项 `db.sqlite_path`（见 `doc/CONFIGURATION.md`）。

单目录模式（默认）：

```text
data/medaudit_diff.db
```

多监控模式（`watch.root_dirs`）：

```text
data/<watch_name>/medaudit_diff.db
```

## 1.3 初始化动作（当前实现）

`_init_db()` 执行以下操作：

- 设置 `PRAGMA journal_mode=WAL;`
- `CREATE TABLE IF NOT EXISTS ...` 创建所有核心表
- 调用 `_ensure_compare_jobs_columns()` 做兼容补列
- 创建常用索引（`CREATE INDEX IF NOT EXISTS ...`）

说明：

- 属于“幂等初始化”：重复运行不会重复创建表
- 属于“轻量迁移”：当前只对 `compare_jobs` 做缺失列补齐（`batch_id`, `report_subdir_name`）

## 2. SQLite 连接与事务模型（代码行为）

`DiffRepository` 的访问模式是“短连接 + 事务上下文”：

- 每次操作通过 `_managed_conn()` 打开一个连接
- 成功则 `commit()`
- 异常则 `rollback()`
- 最后关闭连接

当前连接设置：

- `row_factory = sqlite3.Row`（便于按列名取值）
- 启用 `WAL` 模式（由 `_init_db()` 设置）

注意：

- schema 声明了外键，但当前代码未显式设置 `PRAGMA foreign_keys = ON`
- 因此不要依赖 SQLite 在运行时强制执行外键约束（以代码流程一致性为主）

## 3. 表结构总览（ER 关系概念）

高层关系（逻辑上）：

```text
compare_batches (1) --- (N) compare_jobs
compare_jobs    (1) --- (N) file_snapshots
compare_jobs    (1) --- (1) schema_diffs
compare_jobs    (1) --- (1) diff_summaries
compare_jobs    (1) --- (N) row_diffs
compare_jobs    (1) --- (N) cell_diffs   [via job_id + match_group_id correlation]
compare_jobs    (1) --- (N) reports
compare_jobs    (1) --- (1) ai_summaries
compare_jobs    (1) --- (N) job_logs
compare_batches (1) --- (N) batch_reports
```

## 3.1 ER 图（ASCII）

下面这个 ASCII 图更偏“排错视角”，强调从 `batch -> job -> diff/report/log` 的追踪路径。

```text
                               +----------------------+
                               |    compare_batches   |
                               |----------------------|
                               | id (PK)              |
                               | batch_slug (UNIQUE)  |
                               | status               |
                               | left/right_folder    |
                               +----------+-----------+
                                          |
                              1           |           N
                                          |
                               +----------v-----------+
                               |     compare_jobs     |
                               |----------------------|
                               | id (PK)              |
                               | batch_id (FK-ish)    |
                               | status               |
                               | left/right_csv_path  |
                               | left/right_sha256    |
                               | report_subdir_name   |
                               +--+--+--+--+--+--+--+
                                  |  |  |  |  |  |
                     1..N         |  |  |  |  |  |         1..N
                                  |  |  |  |  |  +-------> +-----------------+
                                  |  |  |  |  |            |    job_logs      |
                                  |  |  |  |  |            +-----------------+
                                  |  |  |  |  |
                                  |  |  |  |  +-----------> +-----------------+
                                  |  |  |  |               |     reports      |
                                  |  |  |  |               +-----------------+
                                  |  |  |  |
                                  |  |  |  +--------------> +-----------------+
                                  |  |  |                  |   ai_summaries   |
                                  |  |  |                  +-----------------+
                                  |  |  |
                                  |  |  +---------------> +-------------------+
                                  |  |                    |     row_diffs      |
                                  |  |                    | (match_group_id)   |
                                  |  |                    +---------+---------+
                                  |  |                              |
                                  |  |                              | correlate by
                                  |  |                              | (job_id, match_group_id)
                                  |  |                              v
                                  |  |                    +-------------------+
                                  |  |                    |     cell_diffs     |
                                  |  |                    +-------------------+
                                  |  |
                                  |  +---------------> +-------------------+
                                  |                    |   diff_summaries   |
                                  |                    +-------------------+
                                  |
                                  +------------------> +-------------------+
                                                       |    schema_diffs    |
                                                       +-------------------+

And separately:

compare_batches (1) ---- (N) batch_reports
```

说明：

- `batch_id`、`job_id` 在 schema 中有外键声明，但运行时不要假设 SQLite 一定强制校验（当前代码未显式 `PRAGMA foreign_keys = ON`）
- `cell_diffs` 与 `row_diffs` 的细粒度关联主要依赖 `(job_id, match_group_id)` 组合进行排查
- `reports` / `batch_reports` 仅登记文件路径，不保证磁盘文件仍存在

## 4. 表结构（字段级说明）

以下字段类型与约束来自 `repository.py` 的建表 SQL（当前实现）。

## 4.1 `compare_batches`（批次表）

用途：记录一次批量触发（一个目录对，可能包含多个 CSV 文件任务）的元数据与状态。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 批次主键 |
| `batch_slug` | TEXT | NOT NULL, UNIQUE | 批次目录标识（如 `results-YYYYMMDDHHMMSS`） |
| `created_at` | TEXT | NOT NULL | 创建时间（UTC ISO 字符串） |
| `trigger_reason` | TEXT | NOT NULL | 触发原因（如 `scan_once`, `manual_cli`, `startup_scan`, `folder_stable`） |
| `left_folder` | TEXT | NOT NULL | 左侧目录路径 |
| `right_folder` | TEXT | NOT NULL | 右侧目录路径 |
| `status` | TEXT | NOT NULL | 批次状态（`running` / `done` / `partial_failed` / `failed`） |
| `summary_html_path` | TEXT |  | 批次总览 `index.html` 绝对路径 |
| `summary_csv_path` | TEXT |  | 批次汇总 `summary.csv` 绝对路径 |
| `error_message` | TEXT |  | 批次级错误信息（如批次 AI 总结失败、批次汇总生成失败） |

## 4.2 `compare_jobs`（文件级任务表）

用途：记录单个 CSV 对比任务的生命周期与关键信息。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 任务主键 |
| `status` | TEXT | NOT NULL | 任务状态（见“状态枚举”） |
| `created_at` | TEXT | NOT NULL | 创建时间（UTC ISO） |
| `started_at` | TEXT |  | 首次进入执行阶段时间 |
| `finished_at` | TEXT |  | 完成/失败时间 |
| `left_folder` | TEXT | NOT NULL | 左侧目录路径 |
| `right_folder` | TEXT | NOT NULL | 右侧目录路径 |
| `left_csv_path` | TEXT | NOT NULL | 左侧 CSV 路径 |
| `right_csv_path` | TEXT | NOT NULL | 右侧 CSV 路径 |
| `left_sha256` | TEXT |  | 左侧文件 SHA256 |
| `right_sha256` | TEXT |  | 右侧文件 SHA256 |
| `trigger_reason` | TEXT |  | 触发原因 |
| `error_message` | TEXT |  | 失败或部分失败原因 |
| `batch_id` | INTEGER |  | 所属批次 ID（兼容迁移补列） |
| `report_subdir_name` | TEXT |  | 批次内文件级报告子目录名（兼容迁移补列） |

## 4.3 `file_snapshots`（文件快照）

用途：记录左右文件的文件系统与解析快照。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `job_id` | INTEGER | NOT NULL | 所属任务 |
| `side` | TEXT | NOT NULL | `left` / `right` |
| `path` | TEXT | NOT NULL | 文件路径 |
| `file_size` | INTEGER | NOT NULL | 文件大小 |
| `mtime` | REAL | NOT NULL | 修改时间戳 |
| `sha256` | TEXT | NOT NULL | 文件哈希 |
| `encoding` | TEXT |  | 解析使用的编码 |
| `delimiter` | TEXT |  | 解析使用的分隔符 |
| `created_at` | TEXT | NOT NULL | 写入时间 |

## 4.4 `schema_diffs`（结构差异摘要）

用途：记录表头与列结构层面的差异（每个 job 唯一一条）。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `job_id` | INTEGER | NOT NULL, UNIQUE | 所属任务（唯一） |
| `added_columns` | TEXT | NOT NULL | JSON 数组 |
| `removed_columns` | TEXT | NOT NULL | JSON 数组 |
| `reordered_columns` | TEXT | NOT NULL | JSON 数组 |
| `left_headers` | TEXT | NOT NULL | JSON 数组 |
| `right_headers` | TEXT | NOT NULL | JSON 数组 |
| `column_count_left` | INTEGER | NOT NULL | 左侧列数 |
| `column_count_right` | INTEGER | NOT NULL | 右侧列数 |
| `created_at` | TEXT | NOT NULL | 写入时间 |

## 4.5 `diff_summaries`（行级汇总摘要）

用途：记录行级对比汇总计数（每个 job 唯一一条）。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `job_id` | INTEGER | NOT NULL, UNIQUE | 所属任务（唯一） |
| `total_rows_left` | INTEGER | NOT NULL | 左侧总行数 |
| `total_rows_right` | INTEGER | NOT NULL | 右侧总行数 |
| `exact_match_rows` | INTEGER | NOT NULL | 完全匹配行数 |
| `added_rows` | INTEGER | NOT NULL | 新增行数 |
| `deleted_rows` | INTEGER | NOT NULL | 删除行数 |
| `suspected_modified_rows` | INTEGER | NOT NULL | 疑似修改行数 |
| `fuzzy_match_enabled` | INTEGER | NOT NULL | 是否启用模糊匹配（0/1） |
| `warnings` | TEXT | NOT NULL | JSON 数组（警告） |
| `created_at` | TEXT | NOT NULL | 写入时间 |

## 4.6 `row_diffs`（行级差异明细）

用途：记录新增/删除/疑似修改行的明细。一个 job 可有多条。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `job_id` | INTEGER | NOT NULL | 所属任务 |
| `row_type` | TEXT | NOT NULL | `added` / `deleted` / `suspected_modified` |
| `row_json` | TEXT |  | JSON（新增/删除行；或疑似修改的左行） |
| `peer_row_json` | TEXT |  | 疑似修改场景下右行 JSON |
| `confidence` | REAL |  | 启发式匹配置信度 |
| `match_group_id` | TEXT |  | 疑似修改组 ID，用于关联 `cell_diffs` |
| `created_at` | TEXT | NOT NULL | 写入时间 |

说明：

- `added` / `deleted` 行通常 `peer_row_json`, `confidence`, `match_group_id` 为空
- `suspected_modified` 行会带左右 row JSON 与 `match_group_id`

## 4.7 `cell_diffs`（单元格差异明细）

用途：记录某个疑似修改行中的字段变化明细。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `job_id` | INTEGER | NOT NULL | 所属任务 |
| `match_group_id` | TEXT | NOT NULL | 对应 `row_diffs.match_group_id` |
| `column_name` | TEXT | NOT NULL | 变化列名 |
| `left_value` | TEXT |  | 左值 |
| `right_value` | TEXT |  | 右值 |
| `confidence` | REAL |  | 行级匹配置信度（冗余存储，便于导出） |
| `created_at` | TEXT | NOT NULL | 写入时间 |

## 4.8 `reports`（文件级报告路径）

用途：登记每个 job 生成的文件级报告路径（可多条）。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `job_id` | INTEGER | NOT NULL | 所属任务 |
| `report_type` | TEXT | NOT NULL | 如 `detailed_html`, `detailed_csv`, `ai_summary_md` |
| `file_path` | TEXT | NOT NULL | 报告文件绝对路径 |
| `created_at` | TEXT | NOT NULL | 写入时间 |

## 4.9 `batch_reports`（批次级报告路径）

用途：登记批次级报告路径（可多条）。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `batch_id` | INTEGER | NOT NULL | 所属批次 |
| `report_type` | TEXT | NOT NULL | 如 `batch_index_html`, `batch_summary_csv`, `batch_ai_summary_md` |
| `file_path` | TEXT | NOT NULL | 报告文件绝对路径 |
| `created_at` | TEXT | NOT NULL | 写入时间 |

## 4.10 `ai_summaries`（文件级 AI 总结）

用途：保存文件级 AI 总结文本及元信息。每个 job 唯一一条。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `job_id` | INTEGER | NOT NULL, UNIQUE | 所属任务（唯一） |
| `model` | TEXT | NOT NULL | 模型名 |
| `prompt_version` | TEXT | NOT NULL | Prompt 版本号 |
| `summary_text` | TEXT | NOT NULL | 总结正文 |
| `token_usage` | TEXT | NOT NULL | JSON（token usage） |
| `created_at` | TEXT | NOT NULL | 写入时间 |

说明：

- 当前数据库中保存的是“文件级 AI 总结”
- 批次级 AI 总结主要以文件形式写入并在 `batch_reports` 中登记路径

## 4.11 `job_logs`（任务日志）

用途：记录任务执行过程中的日志信息，便于排查。

| 列名 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `id` | INTEGER | PK AUTOINCREMENT | 主键 |
| `job_id` | INTEGER | NOT NULL | 所属任务 |
| `level` | TEXT | NOT NULL | `INFO` / `WARNING` / `ERROR` |
| `message` | TEXT | NOT NULL | 日志内容 |
| `created_at` | TEXT | NOT NULL | 写入时间 |

## 5. 索引（当前实现）

`_init_db()` 当前创建以下索引：

- `idx_compare_jobs_hashes` on `compare_jobs(left_sha256, right_sha256)`
- `idx_row_diffs_job_id` on `row_diffs(job_id)`
- `idx_reports_job_id` on `reports(job_id)`
- `idx_compare_jobs_batch_id` on `compare_jobs(batch_id)`
- `idx_batch_reports_batch_id` on `batch_reports(batch_id)`

用途说明：

- 哈希索引用于快速判断是否存在已完成的相同文件对
- `job_id` / `batch_id` 索引用于报告重建与详情查询

## 6. 兼容迁移（当前实现）

当前实现包含一个轻量迁移步骤：`_ensure_compare_jobs_columns()`。

行为：

- 检查 `PRAGMA table_info(compare_jobs)`
- 若缺少 `batch_id` 列，则 `ALTER TABLE ... ADD COLUMN batch_id INTEGER`
- 若缺少 `report_subdir_name` 列，则 `ALTER TABLE ... ADD COLUMN report_subdir_name TEXT`

相关测试：

- `tests/test_repository_migration.py`

这说明仓库当前支持从较早版本的 `compare_jobs` schema 平滑升级到当前结构（至少补齐上述两列）。

## 7. 常见状态值与枚举（查询时常用）

## 7.1 `compare_jobs.status`

常见值（由 `pipeline.py` / `repository.py` 使用）：

- `queued`
- `comparing`
- `persisted`
- `reported`
- `ai_summarized`（中间状态）
- `done`
- `reported_done_ai_failed`
- `failed`

兼容识别值（当前流程可能不主动写入）：

- `duplicate_skipped`

## 7.2 `compare_batches.status`

- `running`
- `done`
- `partial_failed`
- `failed`

## 7.3 `row_diffs.row_type`

- `added`
- `deleted`
- `suspected_modified`

说明：

- `cell_diff` 是导出到 `row_diffs.csv` 的逻辑类型，不是 `row_diffs` 表中的 `row_type` 值（数据库中的单元格差异在 `cell_diffs` 表）

## 8. 用法（如何查看与排查数据库）

以下示例默认数据库路径为 `data/medaudit_diff.db`。多监控模式请替换为 `data/<watch_name>/medaudit_diff.db`。

## 8.1 使用 `sqlite3` 命令行（推荐只读）

查看表列表：

```powershell
sqlite3 data\medaudit_diff.db ".tables"
```

查看某张表结构：

```powershell
sqlite3 data\medaudit_diff.db ".schema compare_jobs"
```

查看索引：

```powershell
sqlite3 data\medaudit_diff.db "PRAGMA index_list(compare_jobs);"
```

查看最近 10 个任务：

```powershell
sqlite3 -header -column data\medaudit_diff.db "SELECT id, status, created_at, trigger_reason, left_csv_path, right_csv_path FROM compare_jobs ORDER BY id DESC LIMIT 10;"
```

查看最近 10 个批次：

```powershell
sqlite3 -header -column data\medaudit_diff.db "SELECT id, batch_slug, status, created_at, trigger_reason FROM compare_batches ORDER BY id DESC LIMIT 10;"
```

## 8.2 查询 Cookbook（按排错场景分类）

下面按“症状/问题场景”组织常用 SQL，便于排查时直接复制。

建议：

- 先定位 `batch`（批次）还是 `job`（单文件任务）层面问题
- 再进入明细表（`diff_summaries` / `row_diffs` / `cell_diffs` / `job_logs`）
- 所有查询默认只读，不建议在排错时直接写库

### 场景 A：我想先看最近发生了什么（快速概览）

#### A1. 最近批次（看整体状态）

```sql
SELECT id, batch_slug, status, created_at, trigger_reason, left_folder, right_folder
FROM compare_batches
ORDER BY id DESC
LIMIT 20;
```

#### A2. 最近任务（看文件级状态）

```sql
SELECT id, batch_id, status, created_at, trigger_reason, left_csv_path, right_csv_path
FROM compare_jobs
ORDER BY id DESC
LIMIT 50;
```

### 场景 B：某个批次失败 / `partial_failed`，我想定位是哪些文件出问题

#### B1. 查某批次下所有任务（基础）

```sql
SELECT j.id, j.status, j.left_csv_path, j.right_csv_path, j.report_subdir_name, j.error_message
FROM compare_jobs j
JOIN compare_batches b ON b.id = j.batch_id
WHERE b.batch_slug = 'results-20260224143010'
ORDER BY j.id;
```

#### B2. 仅看失败或 AI 失败任务（批次内聚焦）

```sql
SELECT j.id, j.status, j.left_csv_path, j.error_message
FROM compare_jobs j
JOIN compare_batches b ON b.id = j.batch_id
WHERE b.batch_slug = 'results-20260224143010'
  AND j.status IN ('failed', 'reported_done_ai_failed')
ORDER BY j.id;
```

#### B3. 批次状态与批次级错误信息

```sql
SELECT id, batch_slug, status, error_message, summary_html_path, summary_csv_path
FROM compare_batches
WHERE batch_slug = 'results-20260224143010';
```

### 场景 C：某个 job 为什么失败（或 AI 为什么失败）

#### C1. 查任务基本信息 + 错误字段

```sql
SELECT id, batch_id, status, created_at, started_at, finished_at,
       left_csv_path, right_csv_path, error_message
FROM compare_jobs
WHERE id = 123;
```

#### C2. 查任务日志（排错首选）

```sql
SELECT level, message, created_at
FROM job_logs
WHERE job_id = 123
ORDER BY id;
```

#### C3. 判断是否是“AI失败但报告已完成”

```sql
SELECT id, status, error_message
FROM compare_jobs
WHERE id = 123
  AND status = 'reported_done_ai_failed';
```

### 场景 D：任务完成了，但我想看差异结果到底是什么

#### D1. 查某任务摘要统计（行级）

```sql
SELECT j.id, j.status, s.total_rows_left, s.total_rows_right, s.exact_match_rows,
       s.added_rows, s.deleted_rows, s.suspected_modified_rows, s.fuzzy_match_enabled
FROM compare_jobs j
LEFT JOIN diff_summaries s ON s.job_id = j.id
WHERE j.id = 123;
```

#### D2. 查某任务结构差异（schema）

```sql
SELECT job_id, added_columns, removed_columns, reordered_columns,
       column_count_left, column_count_right
FROM schema_diffs
WHERE job_id = 123;
```

#### D3. 查疑似修改行（行级）

```sql
SELECT id, row_type, match_group_id, confidence, row_json, peer_row_json
FROM row_diffs
WHERE job_id = 123
  AND row_type = 'suspected_modified'
ORDER BY id
LIMIT 50;
```

#### D4. 查某个疑似修改组的字段变化（cell 级）

```sql
SELECT column_name, left_value, right_value, confidence
FROM cell_diffs
WHERE job_id = 123
  AND match_group_id = 'match_001'
ORDER BY id;
```

### 场景 E：报告文件路径是否已登记（报告缺失/路径错误排查）

#### E1. 查某任务的报告文件路径

```sql
SELECT report_type, file_path, created_at
FROM reports
WHERE job_id = 123
ORDER BY id;
```

#### E2. 查某批次的批次级报告路径

```sql
SELECT report_type, file_path, created_at
FROM batch_reports
WHERE batch_id = 10
ORDER BY id;
```

#### E3. 通过 `batch_slug` 连表查批次级报告

```sql
SELECT b.batch_slug, br.report_type, br.file_path
FROM compare_batches b
JOIN batch_reports br ON br.batch_id = b.id
WHERE b.batch_slug = 'results-20260224143010'
ORDER BY br.id;
```

提示：

- `reports` / `batch_reports` 仅记录“曾写入过的路径”
- 若文件被手工删除，数据库仍可能保留记录；可配合文件系统检查

### 场景 F：`rebuild-report` 前先确认数据库内容是否完整

#### F1. 检查 job 是否存在

```sql
SELECT id, status, batch_id, report_subdir_name
FROM compare_jobs
WHERE id = 123;
```

#### F2. 检查重建所需核心数据是否齐全（摘要 + schema + row diff）

```sql
SELECT
  EXISTS(SELECT 1 FROM schema_diffs   WHERE job_id = 123) AS has_schema,
  EXISTS(SELECT 1 FROM diff_summaries WHERE job_id = 123) AS has_summary,
  EXISTS(SELECT 1 FROM row_diffs      WHERE job_id = 123) AS has_row_diffs,
  EXISTS(SELECT 1 FROM file_snapshots WHERE job_id = 123) AS has_snapshots;
```

#### F3. 检查 AI 总结是否可重写（可选）

```sql
SELECT job_id, model, prompt_version, created_at
FROM ai_summaries
WHERE job_id = 123;
```

### 场景 G：怀疑重复比较 / 相同文件对被多次处理

#### G1. 用哈希对查重复完成任务

```sql
SELECT id, status, created_at, left_sha256, right_sha256
FROM compare_jobs
WHERE left_sha256 = 'LEFT_SHA256'
  AND right_sha256 = 'RIGHT_SHA256'
ORDER BY id DESC;
```

#### G2. 找出最近重复哈希对（聚合视角）

```sql
SELECT left_sha256, right_sha256, COUNT(*) AS cnt,
       MIN(id) AS first_job_id, MAX(id) AS last_job_id
FROM compare_jobs
WHERE left_sha256 IS NOT NULL
  AND right_sha256 IS NOT NULL
GROUP BY left_sha256, right_sha256
HAVING COUNT(*) > 1
ORDER BY cnt DESC, last_job_id DESC
LIMIT 50;
```

### 场景 H：想从 batch 快速跳到“最值得看的文件”

#### H1. 按差异规模排序批次内任务（优先看变化多的）

```sql
SELECT j.id, j.status, j.left_csv_path,
       s.added_rows, s.deleted_rows, s.suspected_modified_rows,
       (COALESCE(s.added_rows,0) + COALESCE(s.deleted_rows,0) + COALESCE(s.suspected_modified_rows,0)) AS diff_score
FROM compare_jobs j
JOIN compare_batches b ON b.id = j.batch_id
LEFT JOIN diff_summaries s ON s.job_id = j.id
WHERE b.batch_slug = 'results-20260224143010'
ORDER BY diff_score DESC, j.id DESC;
```

#### H2. 找“完全无差异”的任务（便于批量跳过）

```sql
SELECT j.id, j.left_csv_path
FROM compare_jobs j
JOIN compare_batches b ON b.id = j.batch_id
JOIN diff_summaries s ON s.job_id = j.id
WHERE b.batch_slug = 'results-20260224143010'
  AND s.added_rows = 0
  AND s.deleted_rows = 0
  AND s.suspected_modified_rows = 0
  AND s.total_rows_left = s.total_rows_right
  AND s.exact_match_rows = s.total_rows_left
ORDER BY j.id;
```

## 8.3 使用 Python 只读查询（示例）

```python
import sqlite3

conn = sqlite3.connect("data/medaudit_diff.db")
conn.row_factory = sqlite3.Row

rows = conn.execute(
    """
    SELECT id, status, created_at, trigger_reason
    FROM compare_jobs
    ORDER BY id DESC
    LIMIT 5
    """
).fetchall()

for row in rows:
    print(dict(row))

conn.close()
```

## 8.4 使用 CLI（推荐的“业务级用法”）

多数场景不需要直接写 SQL，优先使用 CLI：

- `doctor`：检查 SQLite 可写性
- `compare` / `scan-once` / `run`：写入新任务和结果
- `rebuild-report --job-id <id>`：从数据库重建报告

示例：

```powershell
python -m medaudit_diff_watcher --config config.yaml rebuild-report --job-id 123
```

多监控模式：

```powershell
python -m medaudit_diff_watcher --config config.yaml rebuild-report --job-id 123 --watch-name 04_SDTM
```

## 9. 手工操作数据库的注意事项

- 不建议手工 `UPDATE/DELETE` 生产数据（尤其是 `compare_jobs`, `row_diffs`, `cell_diffs`）
- 报告路径是绝对路径，手工迁移目录后路径可能失效
- `reports` / `batch_reports` 是登记表，删除文件不会自动同步删除数据库记录
- `rebuild-report` 依赖数据库内容完整性，不会重新计算 CSV 差异

## 10. 与其他文档的关系

- `doc/ARCHITECTURE.md`：数据库在流水线中的位置（何时写入）
- `doc/REPORTS_AND_STORAGE.md`：报告目录与数据库的高层关系
- `doc/CLI_USAGE.md`：`rebuild-report` 等命令的使用方式
- `doc/TROUBLESHOOTING.md`：数据库常见故障排查场景
