# MedAudit-Diff-Watcher

本项目是一个本地 CSV 差异审计工具，面向“目录版本迭代”场景：

- 监控父目录中新出现的子目录，自动选择最新两版进行比较
- 可自动拉起 Beyond Compare / WinMerge 做人工可视化复核
- Python 生成结构化 CSV 差异结果（行级 + 疑似修改 + 字段变化模式）
- SQLite 持久化结果，生成 HTML/CSV 报告
- 可选 AI 中文总结（单文件 + 批次级）
- 支持单进程多目录监控（`watch.root_dirs`）

## English Summary

MedAudit-Diff-Watcher is a local Python CLI tool for CSV audit diffs across versioned folders.

- Watches a parent folder and compares the latest two subfolders
- Optionally launches Beyond Compare / WinMerge for manual visual review
- Generates structured CSV diff results (row changes + suspected modified rows + field change patterns)
- Persists results to SQLite and renders HTML/CSV reports
- Optionally produces AI summaries (file-level and batch-level)
- Supports multi-watch mode with isolated `data/` and `reports/` storage per watch scope

## Quick Start

### 1) 安装依赖

```powershell
python -m pip install -e .[all]
```

GUI / 托盘首版（可选，零影响并行改造路径）：

```powershell
python -m pip install -e .[gui]
medaudit-diff-watcher-gui --config config.gui-dev.yaml
```

说明：GUI 默认使用独立 `config.gui-dev.yaml`，建议配置单独的监视目录 / DB / 报告目录，避免和当前 CLI 监视同一目录。

### 2) 创建本地配置（使用脱敏模板）

```powershell
Copy-Item config.example.yaml config.yaml
```

至少需要检查并修改这些项：

- `watch.root_dir` 或 `watch.root_dirs`
- `csv.fixed_filename`（固定文件名或通配符，如 `DM.csv` / `*.csv`）
- `csv.exclude_columns_regex`（字段除外规则；默认已忽略 `XXSEQ` 这类字段）
- `compare_tool.executable_path`

建议先保持 `ai.enabled: false` 跑通主流程，再配置 AI。

### 3) 运行环境诊断

注意：`--config` 是全局参数，建议放在子命令前。

```powershell
python -m medaudit_diff_watcher --config config.yaml doctor
```

### 4) 启动监控

```powershell
python -m medaudit_diff_watcher --config config.yaml run
```

### 5) 手动比较（最小可运行示例）

```powershell
python -m medaudit_diff_watcher --config config.yaml compare --left "C:\Study\V1" --right "C:\Study\V2"
```

## 核心能力说明

### Compare Tool（Beyond Compare / WinMerge）

`compare_tool` 支持：

- Beyond Compare（如 `BCompare.exe` / `BComp.exe`）
- WinMerge（如 `WinMergeU.exe`）

`compare_tool.tool` 可选值：

- `auto`（按可执行文件名自动识别）
- `bcompare`
- `winmerge`

`compare_tool.compare_mode` 可选值：

- `file`：打开左右 CSV 文件
- `folder`：打开左右目录（多 CSV 批次时通常更方便）

## CLI 命令总览

- `doctor`：环境与配置检查
- `run`：常驻监控
- `scan-once`：扫描一次并触发必要比较
- `compare --left <dir> --right <dir>`：手动比较两个目录
- `rebuild-report --job-id <id>`：从数据库重建报告

补充：

- 当 `csv.fixed_filename` 使用通配符（如 `*.csv`）时，程序现在会比较左右目录匹配到的文件并集，不再只比较交集
- 若某个 CSV 仅存在于一侧，也会生成完整报告；缺失侧按“空文件”处理，结果会体现为整文件新增或整文件删除

完整参数和示例见 `doc/CLI_USAGE.md`。

## 报告与存储（概要）

新版本按“批次”输出报告：

```text
reports/
  results-YYYYMMDDHHMMSS/
    index.html
    summary.csv
    <csv_stem>/
      detailed_report.html
      row_diffs.csv
      ai_summary.md          # 启用 AI 且成功时生成
    batch_ai_summary.md      # 启用 AI 且成功时生成
```

多监控模式会自动按 `watch_name` 隔离：

```text
reports/<watch_name>/...
data/<watch_name>/medaudit_diff.db
```

详细说明见 `doc/REPORTS_AND_STORAGE.md`。

## 文档导航

- `CHANGELOG.md`：版本变更记录
- `doc/README.md`：文档导航
- `doc/PROJECT_OVERVIEW.md`：项目遍历结果与模块地图
- `doc/ARCHITECTURE.md`：架构与数据流
- `doc/CONFIGURATION.md`：配置项详解
- `doc/CLI_USAGE.md`：CLI 使用说明
- `doc/REPORTS_AND_STORAGE.md`：报告布局与 SQLite 存储
- `doc/DATABASE.md`：SQLite 建库流程、表结构、索引与常用查询
- `doc/DEVELOPMENT.md`：本地开发与测试
- `doc/CHANGELOG_GUIDE.md`：团队改动记录规范（CHANGELOG/变更说明写法）
- `doc/TROUBLESHOOTING.md`：常见问题排查
- `doc/AI_WORK_RULES.md`：AI/Codex 协作规则与 Prompt 模板
- `doc/GUI_DESKTOP_PACKAGING.md`：GUI/托盘首版与 PyInstaller/Inno Setup 打包说明

## 安全提示

- `config.yaml` 通常包含本地路径和 AI 密钥，不应提交到版本库。
- 请使用 `config.example.yaml` 复制生成本地 `config.yaml`。
- 当前项目不会自动展开 `${ENV_VAR}` 这类环境变量占位符；请直接填写实际值，或自行在外部生成配置文件。
