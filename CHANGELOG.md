# Changelog

## v0.1.1 - 2026-03-11

### Summary
- 增加 CSV 字段排除规则配置，并修正通配符比较只处理交集文件的问题。

### Added
- [Config] 新增 `csv.exclude_columns_regex`，支持按正则排除不参与比较的字段。
- [GUI] 配置表单新增 `exclude_columns_regex` 编辑入口。

### Changed
- [CSV Diff] 默认忽略 `^[A-Za-z]{2}SEQ$` 命中的字段，例如 `DMSEQ`、`RSSEQ`、`AESEQ`。
- [Planner/Pipeline] 当 `csv.fixed_filename` 为通配符时，左右目录改为按匹配文件并集生成比较任务。
- [Reports] 某个 CSV 仅存在于一侧时，仍会生成完整报告，缺失侧按空文件处理，结果表现为整文件新增或删除。

### Docs
- 更新 README、配置说明、CLI 使用说明、架构说明、排障说明、报告存储说明和项目总览，使文档与当前实现一致。

### Validation
- `python -m unittest discover -s tests`
- `python -m compileall medaudit_diff_watcher`
