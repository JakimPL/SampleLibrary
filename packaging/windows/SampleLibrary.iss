; scripts/build_installer.py defines Version, Executable, Icon, QuitScript, OutputDirectory and OutputName.
#define AppName "SampleLibrary"

[Setup]
AppId={{63299140-3BC8-420F-A6EB-5D1E6126E58C}
AppName={#AppName}
AppVersion={#Version}
AppVerName={#AppName} {#Version}
AppPublisher=Jakim
AppPublisherURL=https://github.com/JakimPL/SampleLibrary
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDirectory}
OutputBaseFilename={#OutputName}
SetupIconFile={#Icon}
UninstallDisplayIcon={app}\{#AppName}.ico
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#Executable}"; DestDir: "{app}"; DestName: "{#AppName}.exe"; Flags: ignoreversion
Source: "{#Icon}"; DestDir: "{app}"; DestName: "{#AppName}.ico"; Flags: ignoreversion
Source: "{#QuitScript}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; IconFilename: "{app}\{#AppName}.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; IconFilename: "{app}\{#AppName}.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\quit.ps1"""; Flags: runhidden waituntilterminated; RunOnceId: "QuitApplication"
Filename: "{app}\{#AppName}.exe"; Parameters: "self remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemovePackages"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssInstall) and FileExists(ExpandConstant('{app}\{#AppName}.exe')) then
  begin
    ExtractTemporaryFile('quit.ps1');
    Exec('powershell.exe', ExpandConstant('-NoProfile -ExecutionPolicy Bypass -File "{tmp}\quit.ps1"'), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{app}\{#AppName}.exe'), 'self remove', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
