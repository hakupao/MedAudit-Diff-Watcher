# 配置说明（`config.yaml`）

本文档基于 `medaudit_diff_watcher/config.py` 的当前实现编写。

## 使用方式

建议流程：

```powershell
Copy-Item config.example.yaml config.yaml
```

然后按需修改 `config.yaml` 中的本地路径、对比工具路径和 AI 配置。

## 重要说明（请先读）

- 配置文件顶层必须是 YAML 映射（dictionary）
- 当前项目不会自动展开环境变量占位符（例如 `${OPENAI_API_KEY}` 不会自动解析）
- `watch.root_dir` 与 `watch.root_dirs` 至少要提供一个有效路径
- `csv.fixed_filename` 必填且不能为空

## 配置结构总览

```yaml
watch:
pairing:
csv:
diff:
compare_tool:
db:
report:
ai:
logging:
```

## `watch`（监控目录）

### `watch.root_dir: str`

单目录监控模式下的根目录。

- 程序会监控该目录下的子目录
- 默认比较“最新两个子目录”

### `watch.root_dirs: list[str]`

多目录监控模式。

- 非空时优先使用该列表（`root_dir` 会被忽略）
- 每个根目录会生成独立 `watch_name`
- `data/` 和 `reports/` 自动分域隔离

### `watch.scan_interval_sec: int`

轮询扫描间隔（秒），默认 `30`。

### `watch.stable_wait_sec: int`

新目录被发现后，等待目录稳定的秒数，默认 `5`。

### `watch.min_subfolders_to_compare: int`

最少子目录数，小于该值时不会触发最新两版比较，默认 `2`。

## `pairing`（目录配对策略）

### `pairing.strategy: str`

当前实现仅支持：

- `latest_two`

若填写其他值会在运行时触发错误。

## `csv`（CSV 读取与匹配）

### `csv.fixed_filename: str`（必填）

支持两类写法：

- 固定文件名：`DM.csv`
- 通配符：`*.csv`

行为说明：

- 固定文件名：左右目录各取该文件进行比较
- 通配符：程序会取左右目录中匹配文件名的交集，逐文件生成批次内多个任务

### `csv.encoding: str`

- `auto`（推荐）
- 或显式编码（如 `utf-8`, `gbk` 等，取决于实现支持）

### `csv.delimiter: str`

- `auto`（推荐）
- 或显式分隔符（如 `,`, `|`, `\t`）

### `csv.normalize_trim_whitespace: bool`

是否对字段值进行首尾空白裁剪，默认 `true`。

### `csv.normalize_case_headers: bool`

是否对表头进行大小写归一化，默认 `false`。

### `csv.null_equivalents: list[str]`

用于视为“空值”的文本集合，默认包含：

- `""`
- `"NULL"`
- `"null"`
- `"N/A"`

## `diff`（差异算法行为）

### `diff.enable_fuzzy_match: bool`

是否启用启发式/模糊匹配以识别“疑似修改行”，默认 `true`。

### `diff.fuzzy_threshold: int`

模糊匹配阈值，默认 `90`。

### `diff.max_fuzzy_comparisons: int`

模糊匹配比较次数上限，默认 `50000`，用于限制计算开销。

## `compare_tool`（外部可视化比较工具）

### `compare_tool.enabled: bool`

是否启用外部 compare tool 拉起，默认 `true`。

### `compare_tool.tool: str`

支持：

- `auto`
- `bcompare`
- `winmerge`

`auto` 时会基于 `executable_path` 文件名判断。

### `compare_tool.executable_path: str`

可执行文件路径，例如：

- `C:\Program Files\Beyond Compare 5\BCompare.exe`
- `C:\Program Files\WinMerge\WinMergeU.exe`

### `compare_tool.compare_mode: str`

支持：

- `file`
- `folder`

说明：

- `folder` 模式在 `*.csv` 批量比较场景下更常用（通常只拉起一次目录对比）
- `file` 模式会直接打开左右 CSV 文件

## `db`（SQLite 存储）

### `db.sqlite_path: str`

SQLite 文件路径，默认 `data/medaudit_diff.db`。

多目录监控时该路径会自动变为：

```text
data/<watch_name>/medaudit_diff.db
```

## `report`（报告输出）

### `report.output_dir: str`

报告输出根目录，默认 `reports`。

多目录监控时该路径会自动变为：

```text
reports/<watch_name>/
```

## `ai`（可选 AI 总结）

### `ai.enabled: bool`

是否启用 AI 总结。建议先设为 `false` 验证主流程。

### `ai.base_url: str`

OpenAI 兼容接口基址（实现会拼接 `/chat/completions`）。

### `ai.api_key: str`

API Key。请勿提交到仓库。

### `ai.model: str`

模型名（由你的兼容服务决定）。

### `ai.timeout_sec: int`

请求超时秒数，默认 `30`。

### `ai.max_retries: int`

失败重试次数，默认 `2`。

### `ai.send_raw_rows: bool`

是否在 AI payload 中包含部分原始行样本，默认 `false`。

风险说明：

- 开启后可能把更多数据内容发送到外部 API
- 涉及敏感数据时应谨慎评估

## `logging`

### `logging.level: str`

日志级别（会被转为大写），常用：

- `DEBUG`
- `INFO`
- `WARNING`
- `ERROR`

## 单目录配置示例（最小）

```yaml
watch:
  root_dir: "C:\\Study\\04_SDTM"

pairing:
  strategy: latest_two

csv:
  fixed_filename: "DM.csv"

diff:
  enable_fuzzy_match: true

compare_tool:
  enabled: true
  tool: auto
  executable_path: "C:\\Program Files\\Beyond Compare 5\\BCompare.exe"
  compare_mode: folder

db:
  sqlite_path: "data/medaudit_diff.db"

report:
  output_dir: "reports"

ai:
  enabled: false

logging:
  level: INFO
```

## 多目录配置示例（单进程多监控）

```yaml
watch:
  root_dirs:
    - "C:\\StudyA\\04_SDTM"
    - "D:\\StudyB\\04_SDTM"
  scan_interval_sec: 30
  stable_wait_sec: 5
  min_subfolders_to_compare: 2

pairing:
  strategy: latest_two

csv:
  fixed_filename: "*.csv"

diff:
  enable_fuzzy_match: true

compare_tool:
  enabled: true
  tool: winmerge
  executable_path: "C:\\Program Files\\WinMerge\\WinMergeU.exe"
  compare_mode: folder

db:
  sqlite_path: "data/medaudit_diff.db"  # 实际按 watch_name 隔离

report:
  output_dir: "reports"                 # 实际按 watch_name 隔离

ai:
  enabled: false

logging:
  level: INFO
```

## 常见配置错误与修正

### 1) `watch.root_dir or watch.root_dirs must provide at least one path`

原因：没有配置有效监控路径。

修正：设置 `watch.root_dir` 或 `watch.root_dirs`（非空列表）。

### 2) `csv.fixed_filename must not be empty`

原因：`csv.fixed_filename` 缺失或空字符串。

修正：设置为 `DM.csv` 或 `*.csv` 等有效值。

### 3) compare tool 路径存在但无法启动

常见原因：

- 路径指向错误版本或文件名
- 权限问题
- 工具未正确安装

建议先运行：

```powershell
python -m medaudit_diff_watcher --config config.yaml doctor
```

