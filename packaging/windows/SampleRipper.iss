; scripts/build_installer.py defines Version, Executable, NvidiaExecutable, MinimumCudaMajor, Icon,
; QuitScript, OutputDirectory and OutputName.
#define AppName "SampleRipper"

[Setup]
AppId={{63299140-3BC8-420F-A6EB-5D1E6126E58C}
AppName={#AppName}
AppVersion={#Version}
AppVerName={#AppName} {#Version}
AppPublisher=Jakim
AppPublisherURL=https://github.com/JakimPL/SampleRipper
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
Source: "{#Executable}"; DestDir: "{app}"; DestName: "{#AppName}.exe"; Flags: ignoreversion; Check: not HasNvidiaDriver
Source: "{#NvidiaExecutable}"; DestDir: "{app}"; DestName: "{#AppName}.exe"; Flags: ignoreversion; Check: HasNvidiaDriver
Source: "{#Icon}"; DestDir: "{app}"; DestName: "{#AppName}.ico"; Flags: ignoreversion
Source: "{#QuitScript}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; IconFilename: "{app}\{#AppName}.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; IconFilename: "{app}\{#AppName}.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\quit.ps1"" -Executable ""{app}\{#AppName}.exe"""; Flags: runhidden waituntilterminated; RunOnceId: "QuitApplication"
Filename: "{app}\{#AppName}.exe"; Parameters: "self remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemovePackages"

[Code]
var
  NvidiaDriver: Boolean;

{ nvidia-smi ships with the driver, in System32 or in the NVSMI folder of older drivers. }
function NvidiaSmiPath(): String;
begin
  Result := ExpandConstant('{sys}\nvidia-smi.exe');
  if not FileExists(Result) then
    Result := ExpandConstant('{commonpf64}\NVIDIA Corporation\NVSMI\nvidia-smi.exe');
  if not FileExists(Result) then
    Result := '';
end;

{ The CUDA major version the driver reports in nvidia-smi's header, or 0 where there is no driver to ask. }
function DriverCudaMajor(): Integer;
var
  Tool, Line: String;
  Captured: TExecOutput;
  ResultCode, Index, Start: Integer;
begin
  Result := 0;
  Tool := NvidiaSmiPath();
  if Tool = '' then
    Exit;
  if not ExecAndCaptureOutput(Tool, '', '', SW_HIDE, ewWaitUntilTerminated, ResultCode, Captured) then
    Exit;
  if ResultCode <> 0 then
    Exit;
  for Index := 0 to GetArrayLength(Captured.StdOut) - 1 do
  begin
    Line := Captured.StdOut[Index];
    Start := Pos('CUDA Version:', Line);
    if Start > 0 then
    begin
      Line := Trim(Copy(Line, Start + Length('CUDA Version:'), 16));
      Result := StrToIntDef(Copy(Line, 1, Pos('.', Line) - 1), 0);
      Exit;
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  NvidiaDriver := DriverCudaMajor() >= {#MinimumCudaMajor};
  Result := True;
end;

function HasNvidiaDriver(): Boolean;
begin
  Result := NvidiaDriver;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if (CurStep = ssInstall) and FileExists(ExpandConstant('{app}\{#AppName}.exe')) then
  begin
    ExtractTemporaryFile('quit.ps1');
    Exec('powershell.exe', ExpandConstant('-NoProfile -ExecutionPolicy Bypass -File "{tmp}\quit.ps1" -Executable "{app}\{#AppName}.exe"'), '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    Exec(ExpandConstant('{app}\{#AppName}.exe'), 'self remove', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;
