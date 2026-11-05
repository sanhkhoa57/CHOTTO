param([string]$Start, [string]$Out)
# Hộp chọn thư mục kiểu Explorer (thanh địa chỉ, ô tìm kiếm, thư mục hay dùng) cho bộ cài CHOTTO.
# Kết quả ghi vào file $Out (một dòng: đường dẫn thư mục đã chọn); hủy thì không ghi gì.
Add-Type -AssemblyName System.Windows.Forms
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true; $owner.ShowInTaskbar = $false; $owner.Opacity = 0
$owner.StartPosition = 'CenterScreen'; $owner.Show()
$dlg = New-Object System.Windows.Forms.OpenFileDialog
$dlg.Title = 'Chọn thư mục để cài CHOTTO'
$dlg.ValidateNames = $false; $dlg.CheckFileExists = $false; $dlg.CheckPathExists = $true
$dlg.FileName = 'Chọn thư mục này'
if ($Start -and (Test-Path -LiteralPath $Start)) { $dlg.InitialDirectory = $Start }
elseif ($Start -and (Test-Path -LiteralPath (Split-Path -Parent $Start))) { $dlg.InitialDirectory = Split-Path -Parent $Start }
if ($dlg.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
    $folder = [System.IO.Path]::GetDirectoryName($dlg.FileName)
    if ($folder) { [System.IO.File]::WriteAllText($Out, $folder, (New-Object System.Text.UTF8Encoding($true))) }
}
$owner.Close()
