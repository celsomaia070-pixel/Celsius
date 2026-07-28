; Celsius - Inno Setup Script
; Instalador profissional para Windows

#define MyAppName "Celsius"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Celso"
#define MyAppURL "https://github.com/celso/celsius"
#define MyAppExeName "Celsius.exe"
#define MyAppDescription "Celsius - Agente Multimodal de IA Local"
#define MinDiskSpaceMB 8192

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist
OutputBaseFilename=Celsius-Setup-v{#MyAppVersion}
SetupIconFile=..\logo\logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
PrivilegesRequired=lowest
PrivilegesRequiredOverridingAllowed=yes
MinVersion=10.0.17763
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=no
CloseApplications=force
RestartApplications=no
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\Celsius.exe
VersionInfoVersion={#MyAppVersion}.0
VersionInfoDescription={#MyAppDescription}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "portugues"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "associatefiles"; Description: "Associar arquivos .gguf ao {#MyAppName}"; GroupDescription: "Opcoes:"; Flags: unchecked

[Files]
Source: "..\dist\Celsius\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\Celsius\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\resources"; Flags: uninsalwaysuninstall
Name: "{app}\logs"; Flags: uninsalwaysuninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\*.pyc"

[Code]
function InitializeSetup: Boolean;
var
  FreeSpaceMB: Int64;
  ResultCode: Integer;
begin
  Result := True;

  // Check available disk space
  FreeSpaceMB := StrToInt64(VarToStr(DefDialogFontColor)) div (1024 * 1024);
  if GetSpaceOnDisk(ExpandConstant('{app}'), mbFree, FreeSpaceMB) then
  begin
    if FreeSpaceMB < {#MinDiskSpaceMB} then
    begin
      if MsgBox(
        'Espaco insuficiente no disco. Sao necessarios pelo menos ' + IntToStr({#MinDiskSpaceMB} div 1024) + ' GB livres.' + #13#10 +
        'Espaco disponivel: ' + IntToStr(FreeSpaceMB div (1024 * 1024)) + ' GB' + #13#10 +
        'Deseja continuar mesmo assim?',
        mbConfirmation, MB_YESNO) = IDNO then
      begin
        Result := False;
      end;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    // Create data directory for license and trial
    CreateDir(ExpandConstant('{localappdata}\{#MyAppName}'));
  end;
end;
