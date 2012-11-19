
#define MyAppName "ServerMetrics Agent"
#define MyAppVersion "1.0"
#define MyAppPublisher "Loadimpact"
#define MyAppURL "http://www.loadimpact.com/"

[Setup]
AppId={{F49A05C3-ECFC-423E-B49D-F9737AF86297}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
;AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={pf}\{#MyAppName}
DefaultGroupName=ServerMetrics
AllowNoIcons=yes
OutputBaseFilename=ServerMetricsSetup(x64)
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "F:\projects\servermetrics\servermetrics\windows-installer\dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "F:\projects\servermetrics\servermetrics\windows-installer\agentremove.cmd"; DestDir: "{app}"; 
Source: "F:\projects\servermetrics\servermetrics\windows-installer\agentsetup.cmd"; DestDir: "{app}"; AfterInstall: UpdateConfigFile;
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[UninstallRun]
Filename: "agentremove.cmd"; WorkingDir: "{app}"; Flags: shellexec waituntilterminated

[Code]
var
  ConfigPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ConfigPage := CreateInputQueryPage(wpSelectDir,
    'Agent information', 'Agent name and token',
    'Please enter a unique name for this agent and the token you received from Loadimpact.com, then click Next.');
  ConfigPage.Add('Agent Name:', False);
  ConfigPage.Add('Agent Token:', False);
  ConfigPage.Values[0] := GetComputerNameString();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  if CurPageID = wpSelectDir then begin     
      ConfigPage.Values[0] := GetIniString('General', 'agent_name', GetComputerNameString(), ExpandConstant('{app}\li_metrics_agent.conf'));
      ConfigPage.Values[1] := GetIniString('General', 'server_metrics_token', 'AGENT_TOKEN', ExpandConstant('{app}\li_metrics_agent.conf'));            
  end;
  Result := True;
end;

procedure UpdateConfigFile();
var
  logStr : String;
  ResultCode : Integer;
begin
  {if there is a conf file, leave it.  if not, copy the sample file}
  if Not FileExists(ExpandConstant('{app}\li_metrics_agent.conf')) then
  begin
    FileCopy(ExpandConstant('{app}\li_metrics_agent.conf.sample'),ExpandConstant('{app}\li_metrics_agent.conf'), True);
    logStr := '(''' + ExpandConstant('{app}\li_metrics_agent.log') + ''',)';
    SetIniString('handler_file', 'args', logStr , ExpandConstant('{app}\li_metrics_agent.conf'));
  end;
  
  SetIniString('General', 'agent_name', ConfigPage.Values[0], ExpandConstant('{app}\li_metrics_agent.conf'));
  SetIniString('General', 'server_metrics_token', ConfigPage.Values[1], ExpandConstant('{app}\li_metrics_agent.conf'));
  Exec(ExpandConstant('{app}\agentsetup.cmd'), '', '', SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode); 
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) then
  begin
  end;
end;
