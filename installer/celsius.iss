; Celsius - Inno Setup Script
; Instalador profissional para Windows

#define MyAppName "Celsius"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Celsius Project AI"
#define MyAppURL "https://github.com/celsomaia070-pixel/Celsius"
#define MyAppExeName "Celsius.exe"
#define MyAppDescription "Celsius - Agente Multimodal de IA Local"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist
OutputBaseFilename=Celsius-Setup-v{#MyAppVersion}
SetupIconFile=..\logo\logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
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

[Files]
Source: "..\dist\Celsius\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Dados do cliente ficam fora da pasta do programa e sobrevivem a atualizacoes.
    CreateDir(ExpandConstant('{localappdata}\{#MyAppName}'));
  end;
end;
