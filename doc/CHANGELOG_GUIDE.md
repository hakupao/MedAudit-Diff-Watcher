# 团队改动记录规范（CHANGELOG Guide）

本文档定义团队在本仓库记录改动（CHANGELOG / 发布说明 / PR 变更摘要）时的统一写法。

目标：

- 提高变更可读性与可检索性
- 明确“行为变化”与“内部重构”的区别
- 降低发布时遗漏文档/兼容性说明的风险

## 适用范围

适用于以下场景：

- 手工维护 `CHANGELOG.md`（若仓库后续引入）
- Release Notes（版本发布说明）
- PR/合并说明中的“改动摘要”
- 内部交付记录（给 QA / 使用者 / 运维）

## 基本原则

1. 先写“用户会感知到什么变化”，再写实现细节
2. 使用事实描述，不写夸张结论
3. 明确兼容性影响（是否需要改配置/迁移/重跑）
4. 能定位到模块时写模块名或文件名
5. 文档改动也要记录（尤其当用法发生变化时）

## 推荐分类（固定）

建议按以下类别组织变更项：

- `Added`：新增功能/新增文档/新增命令
- `Changed`：行为调整、输出格式调整、默认值变化
- `Fixed`：缺陷修复
- `Docs`：纯文档更新（不改运行行为）
- `Refactored`：重构（行为不变）
- `Deprecated`：废弃但仍兼容
- `Removed`：移除功能/参数/兼容逻辑
- `Security`：安全相关修复或规则变更

说明：

- 如果是纯文档变更，优先放 `Docs`
- 如果既修 bug 又改文档，分别写到 `Fixed` 和 `Docs`

## 单条记录模板（推荐）

每条记录建议包含 3 个元素：

- 变化内容（做了什么）
- 影响范围（谁会受影响）
- 操作建议（是否需要动作）

模板：

```text
- [模块/范围] 做了什么；影响谁/什么场景；是否需要额外操作（如更新配置、重建报告、指定参数）。
```

示例：

```text
- [CLI] `rebuild-report` 在多监控场景下对重复 `job_id` 提示显式指定 `--watch-name`；影响多目录配置用户；已有单目录配置无需操作。
- [Docs] 新增 `config.example.yaml` 并更新 README 快速开始；影响新用户上手流程；建议从模板复制生成本地 `config.yaml`。
```

## 发布级摘要模板（版本说明）

推荐结构：

1. Summary（1-3 行）
2. Highlights（关键变化，面向使用者）
3. Compatibility / Migration（兼容性与迁移）
4. Notes（已知限制、后续计划，可选）

示例骨架：

```markdown
## vX.Y.Z - YYYY-MM-DD

### Summary
- [一句话概述本次版本主题]

### Added
- ...

### Changed
- ...

### Fixed
- ...

### Docs
- ...

### Compatibility / Migration
- [是否需要更新 config / 重建报告 / DB 迁移说明]
```

## PR / 合并说明建议写法（精简版）

当不维护正式 CHANGELOG 时，至少在 PR 描述里写：

1. What changed
2. Why
3. Risk / compatibility impact
4. Validation (tests / manual checks)

建议格式：

```markdown
## What changed
- ...

## Why
- ...

## Risk / Compatibility
- ...

## Validation
- ...
```

## 本仓库特别要求（MedAudit-Diff-Watcher）

以下变更必须明确写入 changelog/release notes/PR 摘要：

- CLI 子命令或参数变化（`cli.py`）
- 配置项新增/改名/默认值变化（`config.py`）
- 报告目录结构或文件名变化（`reporting.py` / `pipeline.py`)
- SQLite 表结构/状态名变化（`repository.py` / `pipeline.py`）
- AI 请求 payload / prompt 输出结构变化（`ai_client.py`）
- 多监控隔离逻辑变化（`config.py`）

## 应避免的写法（反例）

- “优化了一些逻辑”
- “修复若干问题”
- “调整文档”
- “重构代码（无影响）”但未说明为何无影响

这些写法信息量不足，不利于回溯和排查。

## 高质量变更记录示例（本仓库语境）

```markdown
### Fixed
- [Pipeline] 在 AI 单文件总结失败时保留已生成的 HTML/CSV 报告，并将任务状态标记为 `reported_done_ai_failed`；影响开启 AI 的批次处理场景；无需重跑历史任务。

### Changed
- [Reports] 批次报告目录统一为 `results-YYYYMMDDHHMMSS/`，文件级报告落在 `<csv_stem>/` 子目录；影响依赖旧路径的外部脚本；如有脚本请改用 `summary.csv` 中的相对路径字段。

### Docs
- [Docs] 新增 `doc/AI_WORK_RULES.md` 与 `doc/CHANGELOG_GUIDE.md`，补充 AI 协作规则和团队变更记录规范；仅文档变更，无运行行为影响。
```

## 维护建议

- 小改动也要写清“影响面”，不要只写实现动作
- 文档改动若改变使用路径（例如配置模板、命令位置）应单独记一条
- 合并前由改动作者自查一次：是否遗漏兼容性说明

