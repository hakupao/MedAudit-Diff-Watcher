; Inno Setup installer script (GUI/tray app)
; Build the PyInstaller onedir output first, then adjust SourceDir if needed.

#define AppName "MedAudit Diff Watcher"
#define AppVersion "0.1.0"
#define AppPublisher "Local"
#define AppExeName "medaudit-diff-watcher-gui.exe"
#define DistDir "..\\..\\dist\\medaudit-diff-watcher-gui"

[Setup]
AppId={{8B3F80E9-7E9A-44D8-A6E8-2D12C0AA6A10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\MedAudit Diff Watcher
DefaultGroupName=MedAudit Diff Watcher
AllowNoIcons=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=MedAuditDiffWatcher-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\MedAudit Diff Watcher"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\MedAudit Diff Watcher"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "autostart"; Description: "Start when I log in (Current User)"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch MedAudit Diff Watcher"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MedAuditDiffWatcher"; ValueData: """{app}\{#AppExeName}"" --hide"; Tasks: autostart

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    MsgBox(
      'Note:' + #13#10 +
      'The installer stores program files in Program Files, but GUI config/data/reports should use user-writable paths ' +
      '(for example %LOCALAPPDATA%\MedAuditDiffWatcher). ' +
      'The first GUI launch creates config.gui-dev.yaml if missing.',
      mbInformation,
      MB_OK
    );
  end;
end;

