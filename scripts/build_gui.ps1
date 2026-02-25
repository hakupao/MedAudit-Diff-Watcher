param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

Write-Host "[1/3] Installing GUI build dependencies..."
& $Python -m pip install pyinstaller "PySide6>=6.6"

Write-Host "[2/3] Building GUI (PyInstaller onedir)..."
& $Python -m PyInstaller --noconfirm packaging\pyinstaller\medaudit_diff_watcher_gui.spec

Write-Host "[3/3] Done. Build output:"
Write-Host "  dist\\medaudit-diff-watcher-gui\\"
Write-Host "To build the installer, open packaging\\inno\\MedAuditDiffWatcher.iss in Inno Setup Compiler."

