@echo off
REM Đóng gói CHOTTO thành bộ cài Setup (không hiện cửa sổ console). Cần: pip install -r requirements.txt
REM và Inno Setup 6 (winget install JRSoftware.InnoSetup). Kết quả: dist\CHOTTO-Setup-<phiên bản>.exe
REM Dùng --onedir thay vì --onefile: bản onefile phải giải nén ra %TEMP% mỗi lần bấm link
REM (chậm 1-3 giây, dễ bị antivirus chặn), không hợp với vai trò trình duyệt mặc định.
setlocal
cd /d "%~dp0\.."
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
    echo Can Python 3.11 tro len.
    exit /b 1
)
REM Icon đã có sẵn trong repo; chỉ sinh lại (cần Pillow) khi muốn đổi ảnh: python tools\make_icon.py
if not exist packaging\chotto.ico (
    %PY% tools\make_icon.py
    if errorlevel 1 exit /b 1
)
for /f "delims=" %%v in ('%PY% -c "import chotto; print(chotto.__version__)"') do set "VERSION=%%v"
REM chotto\web: giao diện HTML (HTML/CSS/JS + font). --collect-all webview: pywebview và WebView2 loader.
%PY% -m PyInstaller --noconfirm --clean --noconsole --onedir --name CHOTTO --icon packaging\chotto.ico ^
    --add-data "chotto\data;chotto\data" ^
    --add-data "chotto\web;chotto\web" ^
    --collect-all webview ^
    main.py
if errorlevel 1 (
    echo Dong goi that bai.
    exit /b 1
)
set "ISCC="
for %%p in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%p set "ISCC=%%~p"
if not defined ISCC (
    echo Xong thu muc dist\CHOTTO\CHOTTO.exe, nhung chua co Inno Setup 6 nen chua tao duoc bo cai.
    echo Cai: winget install JRSoftware.InnoSetup  roi chay lai file nay.
    exit /b 1
)
"%ISCC%" /Qp /DAppVersion=%VERSION% packaging\chotto.iss
if errorlevel 1 (
    echo Tao bo cai that bai.
    exit /b 1
)
copy /y "dist\CHOTTO-Setup-%VERSION%.exe" "dist\CHOTTO-Setup.exe" >nul
echo Xong: dist\CHOTTO-Setup-%VERSION%.exe (ban sao ten co dinh: dist\CHOTTO-Setup.exe, dung cho link tai tren trang web)
%PY% toolsuild_downloads.py
endlocal
