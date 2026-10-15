; Inno Setup script for PrintHub (https://jrsoftware.org/isinfo.php)
; Build the bundle first (packaging/windows/build-windows.ps1 runs PyInstaller),
; then compile:  iscc packaging\windows\printhub.iss

#define AppName "PrintHub"
#define AppVersion "0.2.1"
#define AppExe "PrintHub.exe"

[Setup]
AppId={{7C2B9E4A-3F1D-4A6B-9E2C-PRINTHUB0001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=PrintHub contributors
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\..\dist
OutputBaseFilename=PrintHub-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
SetupIconFile=..\assets\printhub.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; The PyInstaller onedir output.
Source: "..\..\dist\PrintHub\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch PrintHub"; Flags: nowait postinstall skipifsilent
