# 项目总览（遍历结果）

本文档用于沉淀一次“全项目遍历”的结果，帮助新维护者快速建立代码地图。

## 项目定位

`MedAudit-Diff-Watcher` 是一个本地运行的 Python CLI 工具，用于：

- 监控某个父目录下的新子目录（版本批次）
- 自动选择最新两个子目录进行 CSV 比较
- 输出差异报告（HTML/CSV）
- 将结果持久化到 SQLite
- 可选生成 AI 中文总结（单文件 + 批次）

## 目录结构概览

```text
MedAudit-Diff-Watcher/
  medaudit_diff_watcher/          # 主代码
  tests/                          # 单元/集成测试（unittest）
  data/                           # 运行期 SQLite 数据（已加入 .gitignore）
  reports/                        # 运行期报告输出（已加入 .gitignore）
  README.md                       # 项目入口文档
  config.example.yaml             # 脱敏配置模板
  config.yaml                     # 本地配置（可能含敏感信息，不应提交）
  pyproject.toml                  # 项目元数据与 console script
```

补充说明：

- `.gitignore` 已忽略 `data/`、`reports/`、`*.db` 等运行产物。
- `medaudit_diff_watcher.egg-info/` 为本地安装后的构建/元数据目录，通常不作为核心阅读对象。

## 关键入口

- Python 模块入口：`medaudit_diff_watcher/__main__.py`
- CLI 主入口：`medaudit_diff_watcher/cli.py`
- 控制台脚本入口（`pyproject.toml`）：`medaudit-diff-watcher = medaudit_diff_watcher.cli:main`

## 核心模块职责（按文件）

### 调度与入口

- `medaudit_diff_watcher/cli.py`
  - 解析 CLI 参数
  - 装配 `PipelineRunner`
  - 管理单监控/多监控场景
  - 处理 `run/scan-once/compare/rebuild-report/doctor`

- `medaudit_diff_watcher/watcher.py`
  - 常驻监控服务（轮询 + 可选 watchdog）
  - 监听新增目录并等待稳定后触发处理

### 规划与比较

- `medaudit_diff_watcher/planner.py`
  - 列出子目录、选择最新两个目录（`latest_two`）
  - 根据 `csv.fixed_filename` 构建单文件或通配符批量比较计划
  - 通配符场景按匹配文件并集生成计划，支持单边缺失文件

- `medaudit_diff_watcher/csv_diff.py`
  - CSV 读取、规范化、差异计算
  - 支持字段排除规则与单边缺失文件按空文件比较
  - 生成 `CsvDiffResult`

- `medaudit_diff_watcher/models.py`
  - 数据模型定义（快照、schema diff、row diff、batch result 等）
  - AI payload 构建逻辑（`CsvDiffResult.to_ai_payload`）

### 外部工具与 AI

- `medaudit_diff_watcher/compare_tool_launcher.py`
  - 启动 Beyond Compare / WinMerge（支持 `auto` 识别）
  - 按 `file` 或 `folder` 模式构建命令

- `medaudit_diff_watcher/ai_client.py`
  - 组装 AI 请求 payload / prompt
  - 调用 OpenAI 兼容 `/chat/completions`
  - 生成单文件总结与批次总结
  - 对“完全一致”场景使用本地固定模板（避免不必要请求）

### 存储与报告

- `medaudit_diff_watcher/repository.py`
  - SQLite 初始化、迁移兼容（轻量字段补齐）
  - 持久化比较结果、报告路径、AI 总结、日志
  - 提供 `rebuild-report` 所需的数据读取

- `medaudit_diff_watcher/reporting.py`
  - 生成 `detailed_report.html` / `row_diffs.csv`
  - 生成批次 `index.html` / `summary.csv`
  - 写入 `ai_summary.md` / `batch_ai_summary.md`

- `medaudit_diff_watcher/doctor.py`
  - 配置与环境诊断（路径、SQLite、compare tool、可选依赖、AI 连接性）

### 配置与工具函数

- `medaudit_diff_watcher/config.py`
  - 配置 dataclass 模型
  - YAML 加载与校验
  - 多监控 `watch_name` 分配与 data/reports 隔离

- `medaudit_diff_watcher/stability.py`
  - 目录稳定性检查（避免文件仍在写入时触发）

- `medaudit_diff_watcher/utils.py`
  - 时间戳、哈希、JSON、文件名清洗等工具函数

## 执行路径（高层）

### `run`

`cli.py` -> `WatcherService` -> 目录稳定触发 -> `PipelineRunner.process_latest_pairs()`

### `scan-once`

`cli.py` -> `PipelineRunner.process_latest_pairs()`（一次性执行）

### `compare`

`cli.py` -> `PipelineRunner.process_manual_pairs(left, right)`

### `rebuild-report`

`cli.py` -> `PipelineRunner.rebuild_reports(job_id)`（从 SQLite 重建报告，不重新比较 CSV）

## 测试覆盖索引（按文件）

### 核心流程

- `tests/test_pipeline.py`
  - 手动比较落库与报告生成
  - 通配符多 CSV 批处理
  - 批次 slug 格式
  - 重复比较仍生成报告
  - 批次 AI 总结输出路径

- `tests/test_csv_diff.py`
  - 行顺序变化处理
  - 疑似修改行检测
  - 字段排除规则与单边缺失文件处理

- `tests/test_planner.py`
  - 最新两目录选择
  - 固定文件名计划构建
  - 通配符计划构建（并集文件名）

### 配置与兼容

- `tests/test_multi_watch_config.py`
  - 单目录兼容存储路径
  - 多目录 watch_name 隔离与路径拆分

- `tests/test_repository_migration.py`
  - 旧 `compare_jobs` schema 升级兼容（补列）

### Compare Tool 与 AI

- `tests/test_compare_tool_launcher.py`
  - WinMerge 自动识别、错误提示与命令构造

- `tests/test_ai_client.py`
  - 完全一致文件/批次使用固定模板

- `tests/test_ai_payload.py`
  - AI payload 字段变化模式统计结构

## 已知命名注意点

- 实际文件是 `medaudit_diff_watcher/compare_tool_launcher.py`
- 当前仓库中不存在 `medaudit_diff_watcher/bc_launcher.py`

如果 IDE 标签页显示 `bc_launcher.py`，通常是历史文件/临时标签/未落盘文件，不应作为当前实现依据。
