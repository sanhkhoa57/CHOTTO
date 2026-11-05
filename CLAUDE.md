# CHOTTO – ghi chú cho Claude

Trạm kiểm soát link Zalo cho Windows/macOS: chặn link đáng ngờ bằng màn hình cảnh báo có độ trễ cố ý.
Giao tiếp với người dùng bằng **tiếng Việt**. Đọc `README.md` để biết cấu trúc đầy đủ; file này chỉ ghi những gì README không nói.

## Trạng thái (cập nhật 2026-11-05)
- Bản hiện tại **v1.5.0**, nhánh `main` đã push lên https://github.com/sanhkhoa57/CHOTTO (commit mới nhất 5587597).
- v1.5.0 = giao diện HTML mới (phong cách "luxury": nền đen ấm, vàng đồng, chữ serif) thay giao diện Tk cũ, song ngữ EN/VI.
- **Chưa commit:** đổi "AECC" thành "AECCUS" ở chân thanh bên (`chotto/web/app.html`, `app.js`, `i18n.js`). Chưa xem bằng mắt.
- Chưa làm: build thử `.exe` (`packaging\build_windows.bat`), thử trên macOS, tag `v1.5.0`.
- Chưa tracked: `index.html` ở thư mục gốc (không rõ từ đâu, hỏi người dùng trước khi động tới).

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
