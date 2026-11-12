; OrangePet installer — Inno Setup script
; Build with: iscc build\installer.iss  (after running build.ps1 for the exe)
; Prerequisites: Inno Setup 6 (https://jrsoftware.org/isdl.php)

#define MyAppName "橘子专注 OrangePet"
#define MyAppNameEn "OrangePet"
#define MyAppExeName "OrangePet.exe"
#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif
#define MyAppPublisher "OrangePet"

[Setup]
SourceDir=..
AppId={{B7E3F4A2-1D5C-4E9F-A8B3-2C1D4E5F6A7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userpf}\OrangePet
DefaultGroupName=橘子专注 OrangePet
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=OrangePetSetup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName=橘子专注 OrangePet
WizardStyle=modern
SetupIconFile=build\orangepet_icon.ico
LicenseFile=LICENSE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"; Flags: checkedonce

[Files]
; The single-file executable produced by build.ps1
Source: "OrangePet.exe"; DestDir: "{app}"; Flags: ignoreversion
; Pre-create the data directory so the app can write logs immediately
Source: "build\README_DATA.txt"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist
Source: "components\LibreHardwareMonitor\*"; DestDir: "{app}\components\LibreHardwareMonitor"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\橘子专注"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载橘子专注"; Filename: "{uninstallexe}"
Name: "{autodesktop}\橘子专注"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动橘子专注"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: dirifempty; Name: "{app}\data"
Type: dirifempty; Name: "{app}"
