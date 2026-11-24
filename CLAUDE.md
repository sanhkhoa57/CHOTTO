# CHOTTO – ghi chú cho Claude

Trạm kiểm soát link Zalo cho Windows/macOS: chặn link đáng ngờ bằng màn hình cảnh báo có độ trễ cố ý.
Giao tiếp với người dùng bằng **tiếng Việt**. Đọc `README.md` để biết cấu trúc đầy đủ; file này chỉ ghi những gì README không nói.

## Trạng thái (cập nhật 2026-11-05)
- Bản hiện tại **v1.5.0**, nhánh `main` trên https://github.com/sanhkhoa57/CHOTTO (repo công khai, trang tải chạy bằng GitHub Pages từ `index.html`).
- v1.5.0 = giao diện HTML mới (phong cách "luxury": nền đen ấm, vàng đồng, chữ serif) thay giao diện Tk cũ, song ngữ EN/VI. Icon chính: `assets/anime.png`
  (sinh `.ico/.icns/PNG` bằng `tools/make_icon.py`, cần Pillow).
- **Windows: xong và đã thử.** Bộ cài Inno Setup (`platforms/PC/windows/chotto.iss`, build bằng `platforms/PC/windows/build_windows.bat`, giao diện bộ cài tiếng Anh). Gói tải nằm trong `downloads/`:
  `CHOTTO-Windows.zip` (Setup + README.txt) và `chotto-extension-chrome.zip` (extension + README.txt); tạo bằng `tools/build_downloads.py`,
  nội dung hướng dẫn ở `packaging/guides/*.txt`. Đừng chạy `unins000.exe` khi thử: nó gỡ đăng ký handler đang dùng.
- **macOS: xong và đã thử (máy M-series, macOS 26).** Chạy đủ vòng: bấm link trong Zalo → cảnh báo HTML → gỡ thì trả về trình duyệt cũ.
  Gói tải `downloads/CHOTTO-macOS.zip` (dmg + README.txt) tạo bằng `python tools/build_downloads.py macos` (không tham số = windows + extension như cũ).
  Đã thử vai người dùng mới (gắn nhãn quarantine): Gatekeeper báo "không thể xác minh" (KHÔNG phải "bị hỏng"), mở qua Quyền riêng tư & Bảo mật > "Vẫn mở".
  Bản build chỉ chạy chip Apple (Python của uv là aarch64).
- **Build `.app` trên Mac** (dùng Python 3.15 của uv, không cần cài Python khác):
  `mv pyproject.toml pyproject.toml.bak && .venv/bin/python platforms/PC/macos/macos_setup.py py2app; mv pyproject.toml.bak pyproject.toml`
  rồi `codesign --force --deep --sign - dist/CHOTTO.app`. Cài thử: chép vào `~/Applications` + `lsregister -f`. `macos_setup.py` tự vá hai lỗi của Python dựng sẵn:
  `zlib` không có `__file__` (py2app sập) và thiếu Tcl/Tk 9 (`_bundle_tcl_tk`, app chết ngay khi mở).
- **Điều không hiển nhiên trên Mac:**
  - Chạy từ mã nguồn phải dùng `uv run main.py` (`python3` = Python 3.9 của Command Line Tools, không có pywebview → lùi về Tk). Đừng xóa nó: git cần.
  - py2app: `sys.executable` là trình thông dịch trần, nên `ui_host_argv()` gọi bộ khởi chạy `Contents/MacOS/CHOTTO`.
  - Cửa sổ tạo sau `webview.start` ra đen trên Cocoa → `_reload_on_show` tải lại trang khi `shown`.
  - Danh sách "Trình duyệt web mặc định" của Cài đặt KHÔNG liệt kê CHOTTO (không khai báo kiểu tài liệu HTML, cố ý). Nút trong app gọi
    `LSSetDefaultHandlerForURLScheme` qua `osascript -l JavaScript` → macOS tự hỏi xác nhận. Gỡ cũng dùng cách này để trả về trình duyệt cũ.
  - macOS đưa CHOTTO lên trước khi giao link nên `lsappinfo front` luôn là CHOTTO; `platforms/macos.py` lấy app đầu tiên không phải CHOTTO trong `visibleProcessList`.
  - Log `NHAN link host=redirect.zalo.me` là host TRƯỚC khi bóc lớp bọc; host thật xem trong `decisions.db`.
- CI: `.github/workflows/release.yml` chạy khi đẩy tag `v*` (Windows OK, extension đã sửa, macOS lỗi ở bước py2app, chưa rõ nguyên nhân: CI dùng Python 3.13 của
  setup-python nên KHÔNG phải lỗi zlib; máy người dùng chưa có `gh` để xem log). Tag `v1.5.0` đã đẩy nhưng CHƯA có Release.
  Người dùng không cho xóa/tạo lại tag; tải file qua `downloads/` thay vì Release.
- Chưa làm: ký số (Windows SmartScreen; Mac cần Apple Developer 99 USD/năm để công chứng; gợi ý SignPath cho Windows, cần file LICENSE).

## Android (`platforms/android/`, Kotlin + Compose, chưa commit, chưa ký số)
- Logic port từ Python: `Url.kt` (WHATWG), `LinkInspector.kt` (Tầng 2), `Blacklist*.kt` (Tầng 1 + cập nhật bằng WorkManager),
  `AgeLookup.kt` (Tầng 3), `Shield.kt`/`Tiers` (điều phối). Dữ liệu là BẢN CHÉP trong `app/src/main/assets/` (rules.json,
  popular_vn.txt, public_suffix_list.dat, blacklist.seed.txt): sửa `chotto/data` thì chép lại.
- `ParityTest` chạy trên `tests/data/engine_vectors.json` + `url_vectors.json`: phải 0 lệch. Lệnh (JAVA_HOME = jbr của Android Studio):
  `.\gradlew testDebugUnitTest lintDebug assembleRelease`.
- Bẫy đã gặp: `readNBytes`/`toString(Charset)` cần API 33 (minSdk 26 → dùng `readUpTo`); R8 `packageScope` làm app sập lúc mở;
  WorkManager cần keep rules (`keepRules/rules.keep`); KHÔNG `finish()` màn cảnh báo trong `onStop` (onStop đến trễ sau Home
  và nuốt mất link mới); `LinkedBlockingQueue` không nhận null.
- Thử trên máy ảo `Medium_Phone_API_37.0` bằng adb (đặt mặc định: `cmd role add-role-holder android.app.role.BROWSER vn.chotto.app`).
  Bản release phải thử riêng (ký tạm bằng `~/.android/debug.keystore`), vì R8 làm bản release chạy khác bản debug.

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

## Bố cục thư mục theo nền tảng (2026-11-23)
- `platforms/PC/{windows,macos}` = build/bộ cài desktop; `platforms/android`; `platforms/extension`. `chotto/platforms/` (không liên quan) là code Python phụ thuộc hệ điều hành. `packaging/guides/` = file hướng dẫn trong gói tải.
- Trang cài đặt của extension (`src/ui/options.*`) dùng y giao diện app Windows (khung điện thoại, 4 mục, thanh điều hướng nổi). `app.css` do `tools/sync_extension_data.py` sinh từ `chotto/web/style.css` + `app.html` (đừng sửa tay; phần riêng ở `options.css`): sửa CSS app Windows thì chạy lại tool đó.
  Khung rộng 420x880 như cửa sổ app (`_APP_W/_APP_H`), kéo được bằng thanh trên cùng (vị trí lưu `localStorage`). Cài đặt lưu ngay mỗi lần đổi. E2E đã sửa theo trang mới (tab qua `[data-tab]`, nhật ký ở `#recentFull`).
- Xóa nhật ký có ở cả 3 nền tảng: Desktop `logdb.clear()` + tác vụ `clear_log` (có hộp xác nhận), extension thông điệp `log-clear`, Android `LogDb.clear()`.
- `platforms/android`: `ParityTest` đọc vector bằng đường dẫn tương đối `../../../tests/data` (đổi chỗ thư mục thì sửa).
- `build_windows.bat` PHẢI giữ CRLF trong thư mục làm việc (LF + chữ Việt trong REM làm `cmd` chạy sai và để lại file rác như `(3`). Sau khi sửa file bằng công cụ, đổi lại CRLF.
- Gói `downloads/CHOTTO-macOS.zip` chỉ dựng được trên Mac; đã cũ hơn Windows/Android/extension (dựng lại 2026-11-23).

## Cấu trúc `chotto/` (sắp xếp lại 2026-11-23)
- Mọi code phụ thuộc hệ điều hành nằm trong `chotto/platforms/` (`windows.py`, `macos.py`, `linux.py` + `common.py`; thủ thuật
  cửa sổ ở `win32_window.py`/`cocoa_window.py`, chọn qua `window.py`). Đăng ký/mở trình duyệt/tự khởi động/nhận diện Zalo/
  thủ thuật cửa sổ chỉ gọi qua `chotto.platforms.*`. Thêm hàm cho một hệ điều hành thì thêm vào cả `_Backend` trong
  `platforms/__init__.py`. Còn rẽ nhánh `sys.platform` tại chỗ (chưa dời, cố ý): `config.data_dir`, khóa file trong `tier1`,
  `service/ipc.py` (Named Pipe / Unix socket), Apple Event trong `service/app.py`, giao diện Tk dự phòng `ui.py`.
- Dùng chung một chỗ: `config.SETTINGS_KEYS` (khóa cửa sổ cài đặt được sửa), `config.config_stamp()`, `messages.msg()`
  (câu EN/VI của tác vụ; cài/gỡ tiếng Việt dùng câu chi tiết do `platforms` trả về), `util.clamp`/`util.levenshtein`.

## Nhân vật taskbar (`chotto/mascot/`)
- Asset `chotto/mascot/assets/` (pose/mask PNG + `palette.json`) trích từ `design/chotto_mascot_customizer.html` bằng `python tools/extract_mascot.py`.
  Thuật toán tô màu có HAI bản phải khớp từng điểm ảnh: Python `mascot/recolor.py` (taskbar) và `chotto/web/mascot.js` (xem trước trong app); test so bằng Node.
- Chạy trên luồng Tk của agent (`_start_mascot` trong `service/app.py`), chỉ Windows. `LinkHandler.notify` báo `warning_open`/`warning_closed`;
  app lưu cài đặt thì host gửi `config_changed` → `WebUI.on_config_changed` (ngoài ra agent tự stat `config.json` mỗi 1,5 giây).
- Bẫy: Tk `deiconify` luôn kích hoạt cửa sổ dù có `WS_EX_NOACTIVATE` → `_give_back_focus` trả focus sau 30/250/600 ms (lấy cửa sổ trước đó TRƯỚC khi dựng cửa sổ).
- Giao diện Tk dự phòng (`ui.py`) không có mục nhân vật.
- Khởi động nhân vật (`mascot_startup`): `login` (mặc định) | `zalo` (chỉ hiện khi `zalo_processes` đang chạy, `TaskbarMascot._reconcile` kiểm mỗi 1,5 giây qua `platforms.any_process_running`) | `off`
  (`WM_ENDSESSION` do `win32_window.watch_session_end` bắt → `_reset_mascot_on_session_end` ghi `mascot_enabled=false`). Tắt máy cưỡng bức/mất điện thì không reset được.
- Cỡ (2026-11-23): `_BASE_SCALE = 0.30` (cỡ thường), tư thế "Khoan đã!" nhân thêm `_STOP_MUL = 2` (gấp 4 bản đầu). Cửa sổ nhân vật dựng theo cỡ to nhất nên vùng chạy hẹp hơn ở hai đầu.
- Muốn thấy sửa đổi của agent/mascot phải tắt agent cũ (`main.py agent`, `ui-host`) rồi chạy lại: `main.py` chỉ nối vào agent đang chạy.

## Việc đã thử và bỏ
- **Mica/Acrylic (nền mờ Windows 11):** thử 4 cách với pywebview + WinForms đều không ra hiệu ứng (WinForms tô nền đè lên). Người dùng đồng ý bỏ qua.
- Thư mục `design/` (bản demo nháp + mã hiệu ứng chép từ skill taste) và `.taste-skill/` đã vào `.gitignore`; **đừng commit** `design/assets` vì chưa rõ giấy phép.

## Lệnh hay dùng (Windows, venv `.venv`, Python 3.15 qua uv)
```
.venv\Scripts\python.exe -m unittest discover -s tests      # 175 bài, phải qua hết
.venv\Scripts\mypy.exe --strict main.py chotto              # phải sạch
.venv\Scripts\python.exe main.py --force <url>              # xem màn hình cảnh báo thật
.venv\Scripts\python.exe main.py                            # mở cửa sổ ứng dụng
```
- Sửa `chotto/data/*` thì chạy `python tools/sync_extension_data.py` (đồng bộ `platforms/extension/data`) và chép sang `platforms/android/app/src/main/assets/`.
- Chụp màn hình giao diện để tự xem: dùng `shoot.mjs` của skill `design-taste-frontend` (đường dẫn `~/.claude/skills/design-taste-frontend/scripts/`).

## Quy ước làm việc với người dùng
- Người dùng hay sắp hết token: trả lời ngắn gọn, làm trước, hỏi sau với việc nhỏ.
- Chỉ commit/push khi được yêu cầu. Commit kết thúc bằng dòng `Co-Authored-By` theo hướng dẫn của phiên.
- Các file `.html` trong `chotto/web` có hook `impeccable` quét thiết kế; cảnh báo `nested-cards` đã được đánh dấu bỏ qua cho `app.html` (báo nhầm).

## Guardian mode (nhánh `guardian-mode`, tách từ `ui-redesign`, chưa merge)
- Tài liệu đầy đủ: `docs/GUARDIAN-MODE.md` (mô hình đe dọa, cài demo). Lõi: `platforms/extension/src/guardian/*`, công cụ: `tools/guardian.py` (+ `guardian.html`), vector chung `tests/data/guardian_vectors.json` (sinh bằng `tools/gen_guardian_vectors.py`).
- Cờ bật/khóa/secret chỉ đọc từ `chrome.storage.managed` (registry HKLM). ID tiện ích ghim bằng `key` trong manifest; khóa bí mật ngoài repo, `*.pem` trong `.gitignore`.
- E2E Guardian giả lập managed bằng cách ghi đè `chrome.storage.managed.get` trong service worker; cần Chromium của Playwright (`npx playwright install chromium`, đặt `CHROMIUM_PATH` nếu bản không khớp). Không bao giờ ghi registry từ test.
- Heredoc bash có dấu nháy đơn trong nội dung dễ vỡ ở công cụ Bash: ghi script bằng công cụ Write rồi chạy.
- **Guardian UX (làm lại cho người lớn tuổi, 2026-11-21):** màn hình chặn chỉ 2 nút + "Thêm lựa chọn"; bước xin phép tự chép lời nhắn có liên kết tới trang người giám hộ `guardian/index.html` (tĩnh, một file, dữ liệu ở `#fragment`, CSP chặn mạng). Tài liệu: `docs/GUARDIAN-MODE.md` mục 10–12, kịch bản thử nghiệm `docs/THU-NGHIEM-KHA-DUNG.md`.
  - Sửa `guardian/src/*` hoặc mã dùng chung (engine, `view.js`, `guardian/codec.js`, `share.js`, `platforms/extension/data`) thì chạy `python tools/build_guardian_page.py` (test Python kiểm tra file dựng khớp nguồn; `.gitattributes` ghim LF vì CSP ghim băm).
  - Nonce giờ là 12 ký tự bộ chữ 31 ký tự (không I L O 0 1); đổi thì chạy lại `python tools/gen_guardian_vectors.py` (vector chung Python ↔ JS). Managed thêm `guardian_name`, `guardian_page_url` (đổi thì phải chạy lại `make-reg` + Merge `.reg`).
  - E2E trên máy này: `CHROMIUM_PATH=<chrome.exe của ms-playwright/chromium-1248>` và `PYTHONUTF8=1`; ảnh "sau" sinh vào `docs/guardian/ux/after/`.
  - Bẫy công cụ: heredoc Python/bash có tiếng Việt + dấu `\` hoặc nháy đơn dễ hỏng escape; ghi file bằng công cụ Write/Edit.

## Mascot hỏi đáp trên trang tải (2026-11-24)
- Mascot nổi góc phải `index.html` (khối `#mx` + script "mascot chat"): lời thoại theo ngữ cảnh 0 token, nhấn đúp để hỏi, gọi `api/mascot-chat.js` (Vercel `@vercel/node`, khai báo trong `vercel.json`). Gemini Flash-Lite là chính, DeepSeek dự phòng.
- Bộ lọc từ khóa/URL nằm Ở HAI NƠI (script trong `index.html` và `api/mascot-chat.js`): sửa một nơi thì sửa cả hai. Khóa API đặt trong Vercel Environment Variables (mẫu: `.env.example`); `.env`/`.dev.vars` bị `.gitignore` chặn và `.claude/settings.json` cấm đọc. KHÔNG đọc/in `.env`.
- **Mascot taskbar cũng có bong bóng + chat (2026-11-24):** `chotto/mascot/speech.py` (lời thoại, bộ lọc, hạn mức 6/ngày trong `data_dir/mascot_chat.json`, gọi API, vẽ bong bóng bằng Pillow) + `bubble.py` (cửa sổ Tk bám theo nhân vật, ô chat). Nhấn đúp = chat (trước là mở app; menu chuột phải vẫn có "Mở CHOTTO"). App KHÔNG giữ khóa API: gọi `https://chotto.id.vn/api/mascot-chat`; thử nội bộ: `node tools/mascot_dev.js` rồi đặt `CHOTTO_MASCOT_API=http://127.0.0.1:5400/api/mascot-chat` trước `uv run main.py`. Bộ lọc nay ở BA nơi (Python, `index.html`, `api/mascot-chat.js`); `tests/test_speech.py` so danh sách từ khóa giữa ba bản.
- **Vẽ nhân vật taskbar (2026-11-24):** cửa sổ mascot là layered window alpha từng điểm ảnh (`win32_window.LayeredSurface`, `UpdateLayeredWindow`): mỗi khung dựng bằng Pillow rồi đổi ảnh + vị trí trong MỘT lệnh (hết rách hình, viền mịn như web). KHÔNG còn `-transparentcolor`/PhotoImage cho nhân vật; canvas Tk chỉ để nhận chuột. Nhịp: MỌI trạng thái động (chạy, giật mình, thở khi ngủ) 60 khung/giây (`fine_timer` 1 ms bật khi có chuyển động; vòng lặp bù thời gian dựng khung; khung không đổi thì bỏ qua `UpdateLayeredWindow`, khung thở lặp lại được cache trong `_data_cache`); đứng yên hẳn (tư thế "Khoan đã" sau 0,4 giây, giảm chuyển động) thì ~8 khung/giây. Bong bóng thoại (`bubble.py`) vẫn dùng cửa sổ màu khóa.
- **Hình nhân vật vẽ dưới-pixel (2026-11-24):** mỗi khung `_sprite_tile` biến đổi affine (co giãn + xoay + lật + dịch, quanh chân giữa, nội suy bilinear như GPU trên web) từ sprite RGBa cỡ màn hình (`_base`), KHÔNG co ảnh theo số pixel nguyên (cách cũ làm nhịp thở chỉ đổi vài pixel nên nhảy nấc dù 60 khung/giây). Tham số làm tròn 1/16 pixel; khung trùng khung đang hiện thì bỏ qua (`_presented`). Mỗi khung ~2 ms (~10% một nhân ở 60 khung/giây).
- **Cài đặt FPS nhân vật (2026-11-24):** khóa `mascot_fps` (mặc định 60, có trong `SETTINGS_KEYS`), chọn ở Cài đặt > Nhân vật trên taskbar > "Độ mượt" bằng THANH KÉO (số nguyên 10..240, `MASCOT_FPS_RANGE`, lưu khi thả tay). `TaskbarMascot._frame_s` = 1/fps, áp dụng ngay khi lưu (không cần khởi động lại). Đo: 144 đạt ~138 khung/giây thực, CPU ~14%/26% (ngủ/chạy) của một nhân; 15 fps ~3%/7%.
- **Nhân vật chạy trên LUỒNG TK RIÊNG (2026-11-24):** `chotto/mascot/runner.py` (`MascotRunner`, `service/app._start_mascot`) tạo `tk.Tk()` riêng trong luồng `chotto-mascot-tk`; trước đây dùng chung luồng Tk của agent nên lúc cảnh báo (luồng chính chỉ "bơm" Tk mỗi 30 ms trong `webui.present`) hay lúc xử lý link nhân vật bị bóp nhịp/đứng hình. Quy tắc: mọi đối tượng Tk của nhân vật (cửa sổ, `after`, `StringVar(master=...)`) chỉ sống ở luồng đó; ra ngoài chỉ `notify`/`request_reload`/`stop`. Nhân vật xin mở app thì đặt cờ `open_flag`, `drain` ở luồng chính mới gọi `open_settings` (KHÔNG gọi Tk chéo luồng). `MascotRunner.start` hạ `sys.setswitchinterval(0.0005)` (chu kỳ nhường GIL 5 ms làm nhân vật rớt 11 khung/giây khi luồng khác tính toán nặng; còn 0,5 ms thì ~135). Tư thế "Khoan đã!" lắc nhẹ mãi như `ma-wave` trên web (hết hiệu ứng thì đứng yên). `TaskbarMascot` vẫn nhận `root` bất kỳ để test dùng `FakeRoot`.
- **Đổi màu nhân vật nhanh (2026-11-24):** `recolor.py` tính sẵn danh sách điểm ảnh cần tô cho từng tư thế (`candidate_offsets`) và nhớ chung kết quả theo (màu gốc, nhóm, màu đích) trong `_MEMOS` (đổi một ô màu chỉ tính lại nhóm đó); vẫn khớp từng điểm ảnh với `mascot.js` (test so bằng Node). `TaskbarMascot` tô TỪNG tư thế (`recolored_pose`), tư thế đang hiện trước, xong tư thế nào thay ngay tư thế đó (`_poses` là list, có thể có phần tử None lúc đầu); có bộ màu mới hơn thì bỏ dở. Giao diện: ô màu mẫu/Ngẫu nhiên/Đặt lại lưu ngay (gửi lệnh lưu TRƯỚC khi vẽ lại bản xem trước), kéo bảng chọn màu gộp 150 ms. Đo: lưu -> mascot đổi màu trên màn hình 60-100 ms (trước 170-270 ms, chưa tính 350 ms chờ của giao diện).
- **Viền nhân vật kiểu anime (2026-11-24):** `taskbar.outline_sprite` (nét tối 2 px x DPI màu `_OUTLINE_RGB` + đường sáng mảnh `_RIM_RGB` bên ngoài để nổi trên taskbar tối, kèm làm nét nhẹ màu) chạy trong `_base` (một lần mỗi tư thế, không tốn thêm mỗi khung). Chỉ viền phần THÂN (`body_seed`: điểm thuộc nhóm màu 1-6 trong mask), nên zZ, dấu !, vệt bụi không bị viền thành cục đen. Ảnh có lề `_pad`: chân đứng cách đáy ảnh đúng bằng lề (`_sprite_tile` tính theo `foot`). Trang giới thiệu dùng ảnh có viền dựng sẵn `chotto/mascot/assets/web/pose_N.png` (`python tools/make_web_mascot.py`, cùng hàm viền; sửa viền thì chạy lại, đã khai báo trong `vercel.json`). Bản xem trước trong app (`mascot.js`) CHƯA có viền.
