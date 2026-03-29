; Treetime Installer — Inno Setup Script
; Download Inno Setup from https://jrsoftware.org/isinfo.php
; Open this file in Inno Setup Compiler and click Build > Compile

[Setup]
AppName=Treetime
AppVersion=0.1.0
AppPublisher=Canopy Consulting
DefaultDirName={autopf}\Treetime
DefaultGroupName=Treetime
UninstallDisplayIcon={app}\Treetime.exe
OutputDir=installer_output
OutputBaseFilename=TreetimeSetup
SetupIconFile=treetime.ico
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "autostart"; Description: "Start Treetime when Windows starts"; GroupDescription: "Startup:"

[Files]
Source: "dist\Treetime\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Treetime"; Filename: "{app}\Treetime.exe"; IconFilename: "{app}\Treetime.exe"
Name: "{group}\Uninstall Treetime"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Treetime"; Filename: "{app}\Treetime.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Treetime"; ValueData: """{app}\Treetime.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Treetime.exe"; Description: "Launch Treetime"; Flags: nowait postinstall skipifsilent
