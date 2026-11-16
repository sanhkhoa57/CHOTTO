<#
.SYNOPSIS
  Đăng ký (hoặc gỡ) tác vụ Task Scheduler chạy `tools/zero_day_gap.py collect` mỗi 30 phút.

.DESCRIPTION
  Chạy cho USER HIỆN TẠI, không cần quyền Administrator. Đường dẫn Python và thư mục repo được lấy
  tại thời điểm chạy script (hỗ trợ đường dẫn có dấu tiếng Việt và khoảng trắng).
  Mỗi lần chạy nối đuôi kết quả vào .zero-day\collect.log (UTF-8).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\schedule_zero_day.ps1            # đăng ký + chạy thử ngay
  powershell -ExecutionPolicy Bypass -File tools\schedule_zero_day.ps1 -Status    # xem tình trạng
  powershell -ExecutionPolicy Bypass -File tools\schedule_zero_day.ps1 -Remove    # gỡ tác vụ
#>
[CmdletBinding()]
param(
    [switch]$Remove,
    [switch]$Status,
    [int]$IntervalMinutes = 30,
    [string]$TaskName = 'CHOTTO-ZeroDay-Collect'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repo 'tools\zero_day_gap.py'
$dataDir = Join-Path $repo '.zero-day'
$log = Join-Path $dataDir 'collect.log'

if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Đã gỡ tác vụ $TaskName (dữ liệu trong $dataDir được giữ nguyên)."
    } else {
        Write-Host "Không có tác vụ $TaskName."
    }
    return
}

if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { Write-Host "Chưa đăng ký tác vụ $TaskName."; return }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host "Trạng thái: $($task.State); lần chạy cuối: $($info.LastRunTime); kết quả cuối: $($info.LastTaskResult); lần chạy kế: $($info.NextRunTime)"
    if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 8 -Encoding UTF8 }
    return
}

# Ưu tiên pythonw.exe (không bật cửa sổ console mỗi 30 phút); kết quả đã được ghi vào file log.
$python = $null
foreach ($name in 'pythonw.exe', 'python.exe') {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*\WindowsApps\*' } | Select-Object -First 1
    if ($cmd) { $python = $cmd.Source; break }
}
if (-not $python) { throw 'Không tìm thấy Python (pythonw.exe/python.exe) trong PATH.' }
if (-not (Test-Path -LiteralPath $script)) { throw "Không thấy $script" }
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

# Dấu ngoặc kép bao từng đường dẫn vì có khoảng trắng.
$arguments = '"{0}" collect --log "{1}"' -f $script, $log
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description 'CHOTTO: thu thập feed lừa đảo để đo khoảng trống zero-day (đồ án).' -Force | Out-Null
Write-Host "Đã đăng ký $TaskName cho $user, chạy mỗi $IntervalMinutes phút."
Write-Host "  Lệnh: `"$python`" $arguments"
Write-Host "  Log:  $log"
Write-Host "  Gỡ:   powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Remove"

# Chạy thử ngay một lần để xác nhận tác vụ hoạt động.
Start-ScheduledTask -TaskName $TaskName
