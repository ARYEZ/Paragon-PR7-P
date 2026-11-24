; Paragon PR7-P installer (Inno Setup 6).
;   iscc /DAppVersion=0.1.0 installer\pr7p.iss      (after pyinstaller pr7p.spec has made dist\PR7-P)
;
; Per-user (no admin rights) into %LOCALAPPDATA%\Programs\PR7-P, with a Start menu entry; ticked by default,
; PR7-P registers as an image viewer: under "Open with" for pictures and in Settings > Default apps (PR7-P --register, so
; installer and Options share shell.py). Windows doesn't let a program make itself the default: Options opens
; Default apps for that one click. --unregister on uninstall. History, favorites and settings stay.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId is permanent: it's how a new version finds and upgrades the installed one. Never change it.
AppId={{02CE0A66-B141-47AD-9489-ACCB0C53E81C}
AppName=Paragon PR7-P
AppVersion={#AppVersion}
AppVerName=Paragon PR7-P {#AppVersion}
AppPublisher=Paragon
VersionInfoVersion={#AppVersion}
PrivilegesRequired=lowest
DefaultDirName={autopf}\PR7-P
DefaultGroupName=Paragon PR7-P
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=PR7-P-Setup-{#AppVersion}
SetupIconFile=..\pr7p\icons\app.ico
UninstallDisplayIcon={app}\PR7-P.exe
UninstallDisplayName=Paragon PR7-P
WizardStyle=modern
WizardImageFile=wizard-large-1x.bmp,wizard-large-2x.bmp
WizardSmallImageFile=wizard-small-1x.bmp,wizard-small-2x.bmp
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "imageviewer"; Description: "Register PR7-P as an image viewer (Open with, Default apps)"; GroupDescription: "Windows:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PR7-P\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Paragon PR7-P"; Filename: "{app}\PR7-P.exe"; Comment: "Image viewer"
Name: "{autodesktop}\Paragon PR7-P"; Filename: "{app}\PR7-P.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PR7-P.exe"; Parameters: "--register"; Flags: runhidden waituntilterminated; Tasks: imageviewer
Filename: "{app}\PR7-P.exe"; Parameters: "--unregister"; Flags: runhidden waituntilterminated; Tasks: not imageviewer
Filename: "{app}\PR7-P.exe"; Description: "{cm:LaunchProgram,Paragon PR7-P}"; Flags: nowait postinstall skipifsilent
; Updates (Check for Updates runs this installer with /SILENT /relaunch=1): start PR7-P again when done.
Filename: "{app}\PR7-P.exe"; Flags: nowait runasoriginaluser; Check: Relaunch

[UninstallRun]
Filename: "{app}\PR7-P.exe"; Parameters: "--unregister"; Flags: runhidden waituntilterminated; RunOnceId: "Unregister"

[Code]
// True only when the updater asked for it (/relaunch=1): normal and CI installs behave as before.
function Relaunch: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;
