; N-Console Professional Installer - x64
#define MyAppName "N-Console"
#define MyAppVersion "22.0.1"
#define MyPublisher "Mr. Neeraj Kumar (IT System Administration)"
#define MyExeName "N-Console.exe"

[Setup]
AppId={{B8A3A4F1-0F13-4A42-8E5A-9F0D0A2C7A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
AppPublisherURL=https://example.invalid
DefaultDirName={autopf}\N-Console
DefaultGroupName=N-Console
DisableProgramGroupPage=no
OutputDir=.
OutputBaseFilename=N-Console-Setup-x64
SetupIconFile=..\assets\n_console_icon.ico
UninstallDisplayIcon={app}\N-Console.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
ChangesAssociations=no
VersionInfoCompany={#MyPublisher}
VersionInfoDescription=N-Console Network and Remote Administration Console
VersionInfoProductName=N-Console
VersionInfoProductVersion={#MyAppVersion}
Uninstallable=yes
CloseApplications=yes
RestartApplications=no
OutputManifestFile=yes

[Files]
Source: "..\build\N-Console-x64\N-Console\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\assets\n_console_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\N-Console"; Filename: "{app}\N-Console.exe"; WorkingDir: "{app}"; IconFilename: "{app}\n_console_icon.ico"; Comment: "N-Console Network Administration Console"
Name: "{group}\N-Console"; Filename: "{app}\N-Console.exe"; WorkingDir: "{app}"; IconFilename: "{app}\n_console_icon.ico"
Name: "{group}\Uninstall N-Console"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\N-Console.exe"; Description: "Launch N-Console"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\N-Console"
