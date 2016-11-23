
#define MyAppName "Server Metrics Agent"
#define MyAppVersion "1.1.1"
#define MyAppPublisher "Load Impact"
#define MyAppURL "http://loadimpact.com/"

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
OutputBaseFilename=server-metrics-agent-{#MyAppVersion}-win.amd64
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "agentremove.cmd"; DestDir: "{app}"; 
Source: "agentsetup.cmd"; DestDir: "{app}"; AfterInstall: UpdateConfigFile;
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[UninstallRun]
Filename: "agentremove.cmd"; WorkingDir: "{app}"; Flags: shellexec waituntilterminated

[Code]
var
  ConfigPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ConfigPage := CreateInputQueryPage(wpSelectDir,
    'Server metrics agent information', 'Server metrics agent name and token',
    'Please enter a unique name for this server metrics agent and the token found on your account page on loadimpact.com, then click Next.');
  ConfigPage.Add('Server metrics agent name:', False);
  ConfigPage.Add('Server metrics agent token:', False);
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
