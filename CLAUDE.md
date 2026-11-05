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
- **macOS: xong và đã thử (máy M-series, macOS 26).** Chạy đủ vòng: bấm link trong Zalo → cảnh báo HTML → gỡ thì trả về trình duyệt cũ.
  Gói tải `downloads/CHOTTO-macOS.zip` (dmg + README.txt) tạo bằng `python tools/build_downloads.py macos` (không tham số = windows + extension như cũ).
  Đã thử vai người dùng mới (gắn nhãn quarantine): Gatekeeper báo "không thể xác minh" (KHÔNG phải "bị hỏng"), mở qua Quyền riêng tư & Bảo mật > "Vẫn mở".
  Bản build chỉ chạy chip Apple (Python của uv là aarch64).
- **Build `.app` trên Mac** (dùng Python 3.15 của uv, không cần cài Python khác):
  `mv pyproject.toml pyproject.toml.bak && .venv/bin/python packaging/macos_setup.py py2app; mv pyproject.toml.bak pyproject.toml`
  rồi `codesign --force --deep --sign - dist/CHOTTO.app`. Cài thử: chép vào `~/Applications` + `lsregister -f`. `macos_setup.py` tự vá hai lỗi của Python dựng sẵn:
  `zlib` không có `__file__` (py2app sập) và thiếu Tcl/Tk 9 (`_bundle_tcl_tk`, app chết ngay khi mở).
- **Điều không hiển nhiên trên Mac:**
  - Chạy từ mã nguồn phải dùng `uv run main.py` (`python3` = Python 3.9 của Command Line Tools, không có pywebview → lùi về Tk). Đừng xóa nó: git cần.
  - py2app: `sys.executable` là trình thông dịch trần, nên `ui_host_argv()` gọi bộ khởi chạy `Contents/MacOS/CHOTTO`.
  - Cửa sổ tạo sau `webview.start` ra đen trên Cocoa → `_reload_on_show` tải lại trang khi `shown`.
  - Danh sách "Trình duyệt web mặc định" của Cài đặt KHÔNG liệt kê CHOTTO (không khai báo kiểu tài liệu HTML, cố ý). Nút trong app gọi
    `LSSetDefaultHandlerForURLScheme` qua `osascript -l JavaScript` → macOS tự hỏi xác nhận. Gỡ cũng dùng cách này để trả về trình duyệt cũ.
  - macOS đưa CHOTTO lên trước khi giao link nên `lsappinfo front` luôn là CHOTTO; `caller.py` lấy app đầu tiên không phải CHOTTO trong `visibleProcessList`.
  - Log `NHAN link host=redirect.zalo.me` là host TRƯỚC khi bóc lớp bọc; host thật xem trong `decisions.db`.
- CI: `.github/workflows/release.yml` chạy khi đẩy tag `v*` (Windows OK, extension đã sửa, macOS lỗi ở bước py2app, chưa rõ nguyên nhân: CI dùng Python 3.13 của
  setup-python nên KHÔNG phải lỗi zlib; máy người dùng chưa có `gh` để xem log). Tag `v1.5.0` đã đẩy nhưng CHƯA có Release.
  Người dùng không cho xóa/tạo lại tag; tải file qua `downloads/` thay vì Release.
- Chưa làm: ký số (Windows SmartScreen; Mac cần Apple Developer 99 USD/năm để công chứng; gợi ý SignPath cho Windows, cần file LICENSE).

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
