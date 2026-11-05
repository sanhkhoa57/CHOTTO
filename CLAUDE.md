# CHOTTO – ghi chú cho Claude

Trạm kiểm soát link Zalo cho Windows/macOS: chặn link đáng ngờ bằng màn hình cảnh báo có độ trễ cố ý.
Giao tiếp với người dùng bằng **tiếng Việt**. Đọc `README.md` để biết cấu trúc đầy đủ; file này chỉ ghi những gì README không nói.

## Trạng thái (cập nhật 2026-11-05)
- Bản hiện tại **v1.5.0**, nhánh `main` trên https://github.com/sanhkhoa57/CHOTTO (repo công khai, trang tải chạy bằng GitHub Pages từ `index.html`).
- v1.5.0 = giao diện HTML mới (phong cách "luxury": nền đen ấm, vàng đồng, chữ serif) thay giao diện Tk cũ, song ngữ EN/VI. Icon chính: `assets/anime.png`
  (sinh `.ico/.icns/PNG` bằng `tools/make_icon.py`, cần Pillow).
- **Windows: xong và đã thử.** Bộ cài Inno Setup (`packaging/chotto.iss`, build bằng `packaginguild_windows.bat`, giao diện bộ cài tiếng Anh). Gói tải nằm trong `downloads/`:
  `CHOTTO-Windows.zip` (Setup + README.txt) và `chotto-extension-chrome.zip` (extension + README.txt); tạo bằng `tools/build_downloads.py`,
  nội dung hướng dẫn ở `packaging/guides/*.txt`. Đừng chạy `unins000.exe` khi thử: nó gỡ đăng ký handler đang dùng.
- **macOS: CHƯA XÁC NHẬN.** Người dùng báo Mac vẫn hiện giao diện cũ (Tk). Nghi ngờ: `platform_setup.ui_host_argv()` dùng `[sys.executable, "ui-host"]` khi đóng gói,
  có thể sai với py2app (agent thì đi qua `open -b`) nên host không chạy và `build_handler` lùi về Tk. Việc cần làm trên Mac: `git pull`, chạy `python3 main.py --force <url>`,
  đọc `~/Library/Application Support/CHOTTO/chotto.log` (tìm "Giao diện HTML sẵn sàng" hoặc "Không khởi chạy được giao diện HTML").
  Build `.app`: tạm đổi tên `pyproject.toml` rồi `python packaging/macos_setup.py py2app` (py2app từ chối `install_requires`), sau đó `codesign --force --deep --sign - dist/CHOTTO.app`.
  Nút tải macOS trên `index.html` trỏ `releases/latest/download/CHOTTO-macOS.dmg`: file này chưa tồn tại (404).
- CI: `.github/workflows/release.yml` chạy khi đẩy tag `v*` (Windows OK, extension đã sửa, macOS lỗi ở bước py2app, chưa rõ nguyên nhân). Tag `v1.5.0` đã đẩy nhưng CHƯA có Release.
  Người dùng không cho xóa/tạo lại tag; tải file qua `downloads/` thay vì Release.
- Chưa làm: thử trên macOS, SmartScreen/Safe Browsing cảnh báo vì chưa ký số (gợi ý: SignPath cho mã nguồn mở, cần file LICENSE).

## Kiến trúc giao diện (điều không hiển nhiên)
- pywebview bắt buộc chạy trên luồng chính, mà luồng chính của agent thuộc Tk (IPC, Apple Event). Nên agent khởi chạy sẵn tiến trình con `main.py ui-host`
  và nói chuyện bằng từng dòng JSON qua stdin/stdout. Giao thức mô tả ở đầu `chotto/webhost.py`.
- `chotto/service/webui.py` = phía agent; `chotto/webhost.py` = tiến trình giao diện; `chotto/viewmodel.py` = Result → dữ liệu hiển thị.
- **Fail-safe:** host không chạy được/chết giữa chừng thì `build_handler` (`service/app.py`) tự lùi về Tk (`chotto/ui.py`). `CHOTTO_UI=tk` ép dùng Tk.
- **Bảo mật:** host tự kiểm lại thời gian khóa nút "vẫn mở" (không tin JS); đóng cửa sổ bằng cách nào cũng = "không mở".
- Giao diện: `chotto/web/` (`friction.*` = màn hình cảnh báo, `app.*` = cửa sổ ứng dụng, `style.css` dùng chung, `i18n.js` toàn bộ chữ EN/VI).
  Xem thử trong trình duyệt: mở `friction.html?demo` / `app.html?demo` (thêm `&vi` cho tiếng Việt).
- Ngôn ngữ: khóa cấu hình `ui_language` (`en` mặc định | `vi`). Engine và tiện ích trình duyệt luôn viết lý do bằng tiếng Việt;
  bản tiếng Anh dựng lại từ **mã dấu hiệu** trong `viewmodel._REASONS_EN` và `advisor.TIPS_EN/COMBOS_EN`. Thêm mã dấu hiệu mới thì phải thêm bản dịch (có test kiểm tra).
- Font Newsreader + Onest nằm cục bộ trong `chotto/web/fonts` (giấy phép OFL kèm theo), có bộ chữ tiếng Việt.

## Việc đã thử và bỏ
- **Mica/Acrylic (nền mờ Windows 11):** thử 4 cách với pywebview + WinForms đều không ra hiệu ứng (WinForms tô nền đè lên). Người dùng đồng ý bỏ qua.
- Thư mục `design/` (bản demo nháp + mã hiệu ứng chép từ skill taste) và `.taste-skill/` đã vào `.gitignore`; **đừng commit** `design/assets` vì chưa rõ giấy phép.

## Lệnh hay dùng (Windows, venv `.venv`, Python 3.15 qua uv)
```
.venv\Scripts\python.exe -m unittest discover -s tests      # 175 bài; 1 bài lỗi có sẵn từ trước: test_parity ... sync.json
.venv\Scripts\mypy.exe --strict main.py chotto              # phải sạch
.venv\Scripts\python.exe main.py --force <url>              # xem màn hình cảnh báo thật
.venv\Scripts\python.exe main.py                            # mở cửa sổ ứng dụng
```
- Bài `sync.json` lỗi: dữ liệu tiện ích trình duyệt lệch bản Desktop; có thể sửa bằng `python tools/sync_extension_data.py` (chưa chạy, chưa rõ bên nào đúng).
- Chụp màn hình giao diện để tự xem: dùng `shoot.mjs` của skill `design-taste-frontend` (đường dẫn `~/.claude/skills/design-taste-frontend/scripts/`).

## Quy ước làm việc với người dùng
- Người dùng hay sắp hết token: trả lời ngắn gọn, làm trước, hỏi sau với việc nhỏ.
- Chỉ commit/push khi được yêu cầu. Commit kết thúc bằng dòng `Co-Authored-By` theo hướng dẫn của phiên.
- Các file `.html` trong `chotto/web` có hook `impeccable` quét thiết kế; cảnh báo `nested-cards` đã được đánh dấu bỏ qua cho `app.html` (báo nhầm).
