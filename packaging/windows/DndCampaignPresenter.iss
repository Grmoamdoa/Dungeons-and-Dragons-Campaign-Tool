#define MyAppName "DND Campaign Presenter"
#define MyAppExeName "DND Campaign Presenter.exe"

#ifndef AppVersion
  #define AppVersion "1.1.0"
#endif

#ifndef BuildRoot
  #error BuildRoot preprocessor variable is required.
#endif

#ifndef OutputDir
  #define OutputDir AddBackslash(SourcePath) + "output"
#endif

#ifndef OutputBaseFilename
  #define OutputBaseFilename "DND-Campaign-Presenter-" + AppVersion + "-Windows-x64-Setup"
#endif

[Setup]
AppId={{7D819BD3-F92A-43FC-BC64-9A8A9F0F4F7A}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=D&D Campaign Tool Project
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BuildRoot}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
