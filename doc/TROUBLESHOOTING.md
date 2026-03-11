# 常见问题排查

建议排查顺序：

1. 先运行 `doctor`
2. 再看控制台输出
3. 再检查 `reports/` 与 `data/` 是否有新产物

## 1) `watch.root_dir` 不存在 / 不是目录

### 现象

- `doctor` 中 `watch.root_dir` 显示 `FAIL`
- 或运行时报 `Watch root does not exist` / `is not a directory`

### 排查与修复

- 检查 `config.yaml` 中路径是否拼写正确
- Windows 路径建议使用双反斜杠（`\\`）或正斜杠（`/`）
- 确认目录实际存在且当前用户可访问

## 2) `csv.fixed_filename` 不匹配，无法比较

### 现象

- `compare` 报错：`No matching CSV files for pattern ...`
- 或提示某侧 CSV 缺失（`Left CSV missing` / `Right CSV missing`）

### 常见原因

- 文件名写错（大小写/后缀）
- 左右目录文件名不一致
- 使用固定文件名但目录里实际有多个 CSV

### 修复建议

- 固定文件名场景：设置为真实文件名（如 `DM.csv`）
- 多文件场景：设置为通配符（如 `*.csv`）
- 通配符场景会比较左右目录匹配到的文件并集，不要求文件名完全一致
- 若某个文件只存在于一侧，也会生成报告；请重点检查报告中的整文件新增/删除结果

## 3) compare tool 路径不存在或无法启动

### 现象

- `doctor` 中 `compare_tool` 检查失败
- 控制台日志提示可执行文件不存在

### 排查与修复

- 检查 `compare_tool.executable_path`
- 确认安装的是正确程序（Beyond Compare / WinMerge）
- 确认 `compare_tool.tool` 与实际工具一致（或设为 `auto`）
- 暂时可将 `compare_tool.enabled: false`，先验证 CSV diff 主流程

## 4) `watchdog` 未安装

### 现象

- `doctor` 显示 `watchdog (optional): not installed`

### 影响

- 非致命
- 程序会退回轮询模式（仍可运行）

### 修复（可选）

```powershell
python -m pip install watchdog
```

或直接：

```powershell
python -m pip install -e .[all]
```

## 5) `rapidfuzz` 未安装

### 现象

- `doctor` 显示 `rapidfuzz (optional): not installed`

### 影响

- 非致命（取决于差异引擎实现路径）
- 可能影响“疑似修改行”的模糊匹配能力/性能

### 修复（可选）

```powershell
python -m pip install rapidfuzz
```

## 6) AI 接口不可达 / 鉴权失败

### 现象

- `doctor` 中 `ai_connectivity` 失败
- 或任务状态变为 `reported_done_ai_failed`

### 排查项

- `ai.enabled` 是否真的需要开启（可先关闭）
- `ai.base_url` 是否正确、可访问
- `ai.api_key` 是否有效
- `ai.model` 是否存在于你的兼容服务
- 网络代理/公司网络限制

### 说明

- 单文件 AI 总结失败不会丢失已生成的 CSV 差异报告
- 批次级 AI 总结失败可能使批次状态变为 `partial_failed`

## 7) `rebuild-report` 找不到 job 或多监控冲突

### 现象

- `Job ID <id> not found in any configured watch DB.`
- 或提示同一个 `job_id` 存在于多个 DB，要求指定 `--watch-name`

### 修复建议

- 多监控场景显式添加 `--watch-name`
- 确认 `--config` 指向的是正确的配置文件
- 检查对应 `data/<watch_name>/medaudit_diff.db` 是否存在

示例：

```powershell
python -m medaudit_diff_watcher --config config.yaml rebuild-report --job-id 123 --watch-name 04_SDTM
```

## 8) `--config` 放在子命令后导致参数解析异常

### 现象

- 命令看起来正确，但提示未识别参数（尤其是 `--config`）

### 原因

- `--config` 是顶层参数，建议放在子命令前

### 正确示例

```powershell
python -m medaudit_diff_watcher --config config.yaml doctor
```

## 9) 启动后没有生成报告

### 排查顺序

1. `doctor` 是否全部关键项 OK（路径、sqlite、csv.fixed_filename、compare tool）
2. 监控目录下子目录数量是否达到 `watch.min_subfolders_to_compare`
3. 最新两个子目录里是否存在匹配的 CSV
4. 查看控制台日志与 `data/*.db` 是否有任务记录
5. 尝试 `compare --left --right` 手动触发，缩小问题范围
