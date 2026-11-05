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
ButtonBrowse=Chọn thư mục…
ButtonWizardBrowse=Chọn thư mục…
DiskSpaceMBLabel=Cần ít nhất [mb] MB dung lượng trống.
DiskSpaceGBLabel=Cần ít nhất [gb] GB dung lượng trống.
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
Source: "pick_dir.ps1"; DestDir: "{tmp}"; Flags: dontcopy
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

// Nút "Chọn thư mục…": mở hộp thoại kiểu Explorer (thanh địa chỉ, thư mục hay dùng) thay cho hộp dạng cây của Inno Setup.
procedure BrowseClick(Sender: TObject);
var
  ResultCode: Integer;
  OutFile, Chosen: String;
  Lines: TArrayOfString;
begin
  ExtractTemporaryFile('pick_dir.ps1');
  OutFile := ExpandConstant('{tmp}\chotto_dir.txt');
  DeleteFile(OutFile);
  if Exec('powershell.exe',
          '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ' + AddQuotes(ExpandConstant('{tmp}\pick_dir.ps1')) +
          ' -Start ' + AddQuotes(WizardForm.DirEdit.Text) + ' -Out ' + AddQuotes(OutFile),
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if LoadStringsFromFile(OutFile, Lines) and (GetArrayLength(Lines) > 0) then
    begin
      Chosen := RemoveBackslashUnlessRoot(Trim(Lines[0]));
      if Chosen <> '' then
      begin
        // Cài vào thư mục con CHOTTO để file không lẫn với thư mục người dùng vừa chọn (và gỡ cài đặt không đụng tới file khác).
        if CompareText(ExtractFileName(Chosen), 'CHOTTO') <> 0 then
          Chosen := AddBackslash(Chosen) + 'CHOTTO';
        WizardForm.DirEdit.Text := Chosen;
      end;
    end;
  end
  else
  begin
    // Không chạy được PowerShell: dùng hộp chọn thư mục có sẵn của Inno Setup.
    Chosen := WizardForm.DirEdit.Text;
    if BrowseForFolder('Chọn thư mục để cài CHOTTO', Chosen, True) then
      WizardForm.DirEdit.Text := Chosen;
  end;
end;

procedure InitializeWizard;
begin
  WizardForm.DirBrowseButton.OnClick := @BrowseClick;
end;
