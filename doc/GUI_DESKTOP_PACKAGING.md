# GUI / Tray / Packaging (Zero-Impact First)

本文件描述首版 GUI/托盘与安装包方案，目标是在不影响现有 CLI 生产使用的前提下并行推进。

## 原则

- 现有 CLI 命令和参数不变（`run` / `scan-once` / `doctor` 等）
- GUI 通过子进程调用现有 CLI，不直接改 pipeline/watcher 编排
- GUI 默认使用 `config.gui-dev.yaml`（与 `config.yaml` 隔离）
- 不要让 GUI watcher 和 CLI watcher 同时监视同一目录

## GUI 启动（开发）

```powershell
python -m pip install -e .[gui]
python -m medaudit_diff_watcher.gui_launcher --config config.gui-dev.yaml
```

或使用脚本入口（安装后）：

```powershell
medaudit-diff-watcher-gui --config config.gui-dev.yaml
```

首次启动会自动创建 `config.gui-dev.yaml`（若不存在），优先基于 `config.gui-dev.example.yaml` 生成。

## 打包（PyInstaller）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_gui.ps1
```

`PyInstaller` 输出目录：

- `dist\medaudit-diff-watcher-gui\`

## 安装包（Inno Setup）

- 脚本：`packaging\inno\MedAuditDiffWatcher.iss`
- 先完成 `PyInstaller` 打包，再用 Inno Setup Compiler 打开 `.iss` 编译。

## 已实现能力（首版）

- 托盘常驻 GUI（PySide6）
- 通过 subprocess 启动/停止 CLI watcher
- `scan-once` / `doctor` 一次性命令按钮
- GUI 配置 YAML 编辑、导入 `config.yaml` 副本、保存校验
- 读取 SQLite 批次/任务列表并打开现有 HTML/CSV/MD 报告

## 后续建议

- 将 YAML 编辑器逐步升级为结构化表单编辑器
- 为 GUI 增加更细的状态/错误展示（JSON 输出或结构化事件）
- 增加单实例检查与更严格的同目录冲突检测

