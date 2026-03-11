# CLI 使用说明

本文档基于 `medaudit_diff_watcher/cli.py` 当前实现编写。

## 命令入口

可使用两种方式：

- 模块方式：`python -m medaudit_diff_watcher`
- console script：`medaudit-diff-watcher`

下文统一使用模块方式示例。

## 全局参数

### `--config <path>`

- 默认值：`config.yaml`
- 建议放在子命令前（顶层参数）

示例：

```powershell
python -m medaudit_diff_watcher --config config.yaml doctor
```

## 子命令总览

- `doctor`
- `run`
- `scan-once`
- `compare`
- `rebuild-report`

## `doctor`

用途：验证配置和环境可用性。

检查项包括（按当前实现）：

- `watch.root_dir`
- SQLite 可写性
- compare tool 可执行文件路径
- `csv.fixed_filename`
- `csv.exclude_columns_regex`
- `yaml` / `watchdog` / `rapidfuzz` 安装情况
- AI 连接性（当 `ai.enabled: true`）

命令示例：

```powershell
python -m medaudit_diff_watcher --config config.yaml doctor
```

多监控配置下会按 `[watch_name]` 输出每个 scope 的检查结果。

## `run`

用途：启动常驻监控服务。

行为概述：

- 启动时会先做一次 `startup_scan`
- 后续在检测到新目录稳定后触发 `folder_stable`
- 多监控配置下为每个 scope 启动一个 watcher 线程

命令示例：

```powershell
python -m medaudit_diff_watcher --config config.yaml run
```

停止方式：

- `Ctrl+C`

## `scan-once`

用途：扫描一次当前监控目录并触发必要比较（不常驻）。

命令示例：

```powershell
python -m medaudit_diff_watcher --config config.yaml scan-once
```

输出示例（可能类似）：

- `No comparison pair available yet.`
- `Processed batch results-YYYYMMDDHHMMSS (jobs: 1, 2, 3)`

## `compare`

用途：手动指定左右目录进行比较。

参数：

- `--left <dir>`（必填）
- `--right <dir>`（必填）
- `--watch-name <name>`（可选，多监控场景建议指定）

命令示例：

```powershell
python -m medaudit_diff_watcher --config config.yaml compare --left "C:\Study\V1" --right "C:\Study\V2"
```

多监控场景建议：

```powershell
python -m medaudit_diff_watcher --config config.yaml compare --left "C:\StudyA\V1" --right "C:\StudyA\V2" --watch-name 04_SDTM
```

说明：

- 若 `csv.fixed_filename` 为通配符（如 `*.csv`），会对左右目录匹配到的 CSV 并集执行批量比较
- 若某个 CSV 只存在于一侧，仍会生成完整报告；缺失侧按空文件处理，结果表现为整文件新增或整文件删除
- 字段排除规则来自 `csv.exclude_columns_regex`；命中的字段不会参与 schema / 行内容 / 模糊匹配比较
- 若无匹配文件，会抛出 `No matching CSV files for pattern ...`

## `rebuild-report`

用途：从 SQLite 中已持久化的数据重建报告文件（不重新比较 CSV）。

参数：

- `--job-id <int>`（必填）
- `--watch-name <name>`（可选；多监控场景下建议指定）

命令示例：

```powershell
python -m medaudit_diff_watcher --config config.yaml rebuild-report --job-id 123
```

多监控场景（推荐）：

```powershell
python -m medaudit_diff_watcher --config config.yaml rebuild-report --job-id 123 --watch-name 04_SDTM
```

自动选择逻辑（未指定 `--watch-name` 时）：

- 若仅一个 DB 中存在该 `job_id` -> 自动使用该 scope
- 若多个 DB 都有该 `job_id` -> 报错要求指定 `--watch-name`
- 若都没有 -> 报错

## 多监控下 `--watch-name` 使用规则

`--watch-name` 当前只出现在：

- `compare`
- `rebuild-report`

`run` / `scan-once` / `doctor` 会遍历所有 `watch.root_dirs` 对应的 scope。

## 常见命令组合

### 首次配置验证

```powershell
python -m medaudit_diff_watcher --config config.yaml doctor
python -m medaudit_diff_watcher --config config.yaml scan-once
```

### 手动对比一对目录并查看报告

```powershell
python -m medaudit_diff_watcher --config config.yaml compare --left "C:\Study\Version_A" --right "C:\Study\Version_B"
```

然后查看 `reports/` 下最新批次目录。

### 从历史任务重建详细报告

```powershell
python -m medaudit_diff_watcher --config config.yaml rebuild-report --job-id 42
```

## 注意事项

- `--config` 建议始终放在子命令前，避免参数归属歧义
- `doctor` 中 `watchdog` / `rapidfuzz` 显示未安装不一定是致命错误（代码视为 optional）
- compare tool 启动失败不一定阻断 CSV 差异计算（取决于流程阶段和具体错误）
