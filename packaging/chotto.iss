; CHOTTO – bộ cài Windows (Inno Setup 6). Biên dịch bằng packaging\build_windows.bat (cần đã có dist\CHOTTO).
; Luồng cho người dùng: bấm đúp Setup -> chọn thư mục -> Cài đặt -> Hoàn tất. Có sẵn biểu tượng trên Desktop.
; Không cần quyền quản trị: cài vào thư mục của người dùng, đúng với việc CHOTTO ghi cấu hình vào HKCU.
#ifndef AppVersion
  #define AppVersion "1.5.0"
#endif

[Setup]
AppId={{7C1E4B52-5D0A-4F6B-9A83-2E4C5B9D1F70}
AppName=CHOTTO
AppVersion={#AppVersion}
AppVerName=CHOTTO {#AppVersion}
AppPublisher=CHOTTO
DefaultDirName={localappdata}\Programs\CHOTTO
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableDirPage=no
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=CHOTTO-Setup-{#AppVersion}
SetupIconFile=chotto.ico
UninstallDisplayIcon={app}\CHOTTO.exe
UninstallDisplayName=CHOTTO
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Messages]
SetupAppTitle=Cài đặt CHOTTO
SetupWindowTitle=Cài đặt CHOTTO
WizardSelectDir=Chọn thư mục cài đặt
SelectDirDesc=Bạn muốn cài CHOTTO vào đâu?
SelectDirLabel3=CHOTTO sẽ được cài vào thư mục dưới đây.
SelectDirBrowseLabel=Bấm Cài đặt để tiếp tục, hoặc bấm Chọn… để đổi thư mục khác.
ButtonBrowse=Chọn…
ButtonInstall=Cài đặt
ButtonCancel=Hủy
ButtonNext=Tiếp tục
ButtonBack=Quay lại
ButtonFinish=Hoàn tất
WizardInstalling=Đang cài đặt
InstallingLabel=Vui lòng đợi trong lúc CHOTTO được cài vào máy của bạn.
FinishedHeadingLabel=Đã cài xong CHOTTO
FinishedLabelNoIcons=CHOTTO đã được cài vào máy của bạn.
FinishedLabel=CHOTTO đã được cài vào máy của bạn. Biểu tượng CHOTTO đã có trên màn hình Desktop.
RunEntryExec=Mở CHOTTO

[Files]
Source: "..\dist\CHOTTO\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autodesktop}\CHOTTO"; Filename: "{app}\CHOTTO.exe"; IconFilename: "{app}\CHOTTO.exe"
Name: "{autoprograms}\CHOTTO"; Filename: "{app}\CHOTTO.exe"; IconFilename: "{app}\CHOTTO.exe"

[Run]
Filename: "{app}\CHOTTO.exe"; Description: "Mở CHOTTO"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\CHOTTO.exe"; Parameters: "agent-stop"; Flags: runhidden; RunOnceId: "StopAgent"
Filename: "{app}\CHOTTO.exe"; Parameters: "uninstall"; Flags: runhidden; RunOnceId: "Unregister"

[Code]
// Cài đè lên bản cũ: tắt agent đang chạy nền để file không bị khóa.
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  OldExe: String;
begin
  if CurStep = ssInstall then
  begin
    OldExe := ExpandConstant('{app}\CHOTTO.exe');
    if FileExists(OldExe) then
    begin
      Exec(OldExe, 'agent-stop', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Sleep(1500);
    end;
  end;
end;
