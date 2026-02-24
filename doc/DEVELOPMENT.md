# 开发说明

本文档面向本仓库维护者与协作者。

## 环境要求

- Python `>=3.11`（见 `pyproject.toml`）
- Windows（当前 README/配置示例以 Windows 路径和 compare tool 为主）

## 安装方式

### 基础安装

```powershell
python -m pip install -e .
```

### 建议安装（含可选依赖）

```powershell
python -m pip install -e .[all]
```

`[all]` 当前包含：

- `watchdog`（文件系统事件监听，可选）
- `rapidfuzz`（模糊匹配支持，可选）

## 本地开发常用命令

常用运行命令（完整参数说明见 `doc/CLI_USAGE.md`）：

- `python -m medaudit_diff_watcher --config config.yaml doctor`
- `python -m medaudit_diff_watcher --config config.yaml scan-once`
- `python -m medaudit_diff_watcher --config config.yaml run`
- `python -m medaudit_diff_watcher --config config.yaml compare --left "C:\A" --right "C:\B"`

### 运行测试（unittest）

```powershell
python -m unittest discover -s tests -v
```

运行单个测试文件：

```powershell
python -m unittest -v tests.test_pipeline
```

## 测试覆盖概览（当前）

- `tests/test_planner.py`：目录配对与 glob 计划
- `tests/test_csv_diff.py`：差异算法关键行为
- `tests/test_pipeline.py`：落库、报告、批次与 AI 流程集成
- `tests/test_multi_watch_config.py`：多监控配置与路径隔离
- `tests/test_repository_migration.py`：SQLite schema 兼容
- `tests/test_compare_tool_launcher.py`：compare tool 自动识别与命令
- `tests/test_ai_client.py`：AI 固定模板路径
- `tests/test_ai_payload.py`：AI payload 统计结构

## 代码导航建议（阅读顺序）

建议阅读顺序：

1. `medaudit_diff_watcher/cli.py`
2. `medaudit_diff_watcher/config.py`
3. `medaudit_diff_watcher/pipeline.py`
4. `medaudit_diff_watcher/planner.py`
5. `medaudit_diff_watcher/csv_diff.py`
6. `medaudit_diff_watcher/repository.py`
7. `medaudit_diff_watcher/reporting.py`
8. `medaudit_diff_watcher/ai_client.py`

原因：

- `cli.py` 先给出运行面和装配关系
- `pipeline.py` 是主业务编排中心
- `repository.py` / `reporting.py` 决定外部可见产物（DB + 报告）

## 文档维护约定（建议执行）

以下改动应同步更新文档：

- 改 `cli.py` 子命令/参数 -> 更新 `README.md` 与 `doc/CLI_USAGE.md`
- 改 `config.py` 配置项 -> 更新 `config.example.yaml` 与 `doc/CONFIGURATION.md`
- 改 `reporting.py` 输出文件结构 -> 更新 `README.md` 与 `doc/REPORTS_AND_STORAGE.md`
- 改 `repository.py` 存储结构（表/字段/状态） -> 更新 `doc/REPORTS_AND_STORAGE.md` 与相关测试
- 改 `ai_client.py` 外部接口约束/风险 -> 更新 `doc/CONFIGURATION.md` 与 `doc/AI_WORK_RULES.md`
- 发布/版本变更说明 -> 更新 `doc/CHANGELOG_GUIDE.md` 约定下的 CHANGELOG 条目

## 变更前后检查清单（建议）

提交前至少检查：

1. 文档是否与当前实现一致（命令名、配置键名、路径）
2. 新增示例是否脱敏（路径、密钥、业务数据）
3. 是否误引用不存在文件（例如历史命名）
4. 测试是否覆盖了变更的行为边界（如有代码改动）

## 安全与数据处理注意事项

- `config.yaml` 可能包含真实 API Key，不应提交或粘贴到 issue/PR
- 若需要共享配置示例，使用 `config.example.yaml`
- 若需要展示报告截图/日志，先确认是否包含真实业务数据或路径

## 相关文档

- 命令行细节：`doc/CLI_USAGE.md`
- 配置项细节：`doc/CONFIGURATION.md`
- 报告与存储：`doc/REPORTS_AND_STORAGE.md`
- 团队改动记录规范：`doc/CHANGELOG_GUIDE.md`
