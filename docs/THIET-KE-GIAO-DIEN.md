# Thiết kế lại màn hình cảnh báo "Khoan đã!"

Nhận xét của thầy: *giao diện cảnh báo chưa đạt, đang hiển thị hết mọi lý do kỹ thuật, quá nhiều chữ.*
Tài liệu này ghi vấn đề, nguyên tắc, hai phương án bố cục đã cân nhắc, ảnh trước/sau và các quyết định thiết kế.
Nhánh làm việc: `ui-redesign` (tách từ `zero-day-study`, không đụng engine, luật hay điểm số).

## 1. Vấn đề của bản cũ

![Bản cũ trên tiện ích (giả danh Vietcombank)](ui/before/ext-high.png)

| # | Vấn đề | Biểu hiện trong bản cũ |
|---|--------|------------------------|
| 1 | Quá nhiều thông tin kỹ thuật | Liệt kê tối đa 4 lý do ("Tên miền trông như chuỗi ký tự ngẫu nhiên"...), "Phát hiện ở: Tầng 2 – Phân tích tên miền", điểm rủi ro "83/100", thang "An toàn / Đáng ngờ / Nguy hiểm" |
| 2 | Không rõ nên làm gì | Một đoạn lời khuyên 6–7 dòng; nút "Tôi hiểu rủi ro, vẫn mở" to và nằm sát nút an toàn, nổi ngang nút "Đóng, không mở" |
| 3 | Tên miền thật khó nhận ra | Địa chỉ nằm trong khối thứ hai, cùng cỡ chữ với phần còn lại; ký tự đồng hình (chữ `а` Nga trong `vietcombаnk.com`) trông y hệt chữ Latin |

Một màn hình cảnh báo mà người dùng không đọc hết thì không bảo vệ được ai. Bố mẹ của chúng ta sẽ bấm "vẫn mở" chỉ để cho nó biến mất.

## 2. Nguyên tắc

1. **Hiển thị lũy tiến.** Mặc định chỉ có ba thứ: (a) một câu kết luận, (b) tên miền thật, (c) hành động. Mọi thứ khác nằm trong mục thu gọn "Xem vì sao".
2. **Một câu lý do duy nhất, đời thường**, tối đa ~12 từ, chọn theo mức ưu tiên (danh sách đen, rồi kịch bản tổ hợp của `advisor.py`, rồi dấu hiệu riêng mạnh nhất). Không dùng thuật ngữ (tầng, điểm, TLD, RDAP, homoglyph...).
3. **Tên miền thật là nhân vật chính**: chữ lớn, đơn cách (monospace), phần đăng ký đậm, phần còn lại nhạt, phần giống tên ngân hàng được tô sáng, kèm "Trang chính thức của Vietcombank là vietcombank.com.vn".
4. **Mức độ bằng màu + hình + chữ** (không chỉ màu): đáng ngờ = tam giác hổ phách, nguy hiểm = bát giác đỏ, đã chặn = ổ khóa đỏ đậm đặc; mỗi mức có nhãn chữ riêng.
5. **Phân cấp nút**: "Quay lại an toàn" to, màu thương hiệu; "Vẫn mở link" nhỏ, viền mảnh, bị khóa kèm vòng đếm ngược tròn.
6. **Một hành động hữu ích thêm**: "Sao chép địa chỉ" và "Báo cho người gửi" (soạn sẵn câu nhắn). Chỉ chép vào clipboard, không gửi gì ra ngoài.
7. **Chữ ngắn**: tối đa 3 gạch đầu dòng trong "Xem vì sao", mỗi dòng một ý, một biểu tượng.
8. **Cập nhật mượt** khi Tầng 3 trả kết quả muộn: mức chỉ tăng, dòng "Đang xác minh tuổi tên miền…" có chỗ cố định nên bố cục không nhảy.
9. **Truy cập**: tương phản WCAG AA, bàn phím (Esc = quay lại, focus mặc định ở nút an toàn), `aria-live`, tôn trọng `prefers-reduced-motion`, cỡ chữ theo `rem`/`px` co giãn theo DPI.
10. **Giọng điệu** thân thiện, bình tĩnh, không dọa, không đổ lỗi ("Khoan đã!", "Hãy cẩn thận trước khi mở link này").

## 3. Hai phương án bố cục

**Phương án A: thẻ một cột (đã chọn)**

```
+------------------------------------------+
| [ ! ]  Khoan đã! Link nguy hiểm          |   biểu tượng + nhãn mức
|                                          |
|  Giả danh Vietcombank và hối thúc bạn    |   (a) MỘT câu kết luận
|  Đừng đăng nhập hay nhập mã OTP.         |
| +--------------------------------------+ |
| | Link này thật sự dẫn tới             | |
| | [vcb]-digibanks.top /xac-nhan        | |   (b) tên miền thật, tô sáng
| | ✓ Trang chính thức: vietcombank.com.vn| |
| +--------------------------------------+ |
|  Xem vì sao  v                           |   thu gọn (tối đa 3 dòng)
| [        Quay lại an toàn             ]  |   (c) nút chính, to
| [ Sao chép địa chỉ ][ Báo cho người gửi ]|
|        (8) Vẫn mở link                   |   nút phụ, nhỏ, có vòng đếm ngược
+------------------------------------------+
```

**Phương án B: hai cột (kết luận bên trái, hành động bên phải)**

```
+---------------------------+--------------+
| [!] Link nguy hiểm        | [ Quay lại ] |
| Giả danh Vietcombank...   | [ Sao chép ] |
| vcb-digibanks.top/xac-nhan| (8) Vẫn mở   |
| Xem vì sao v              |              |
+---------------------------+--------------+
```

**Chọn A**, vì:
- Một cột chỉ có một đường đọc từ trên xuống: kết luận, địa chỉ, việc cần làm. Người lớn tuổi không phải quét hai vùng.
- Hai cột cần chiều rộng lớn; trên cửa sổ hẹp, điện thoại hay Zalo Web thu nhỏ nó sụp thành một cột và phải thiết kế lại. Phương án A dùng đúng một bố cục ở mọi kích thước (Desktop 620 px, hộp thoại trên Zalo, cỡ điện thoại 390 px).
- Nút chính nằm ở đáy, nơi ngón tay/chuột dừng sau khi đọc; nút "vẫn mở" bị đẩy xuống thấp nhất và nhỏ nhất, đúng ý đồ.
- Một bố cục duy nhất nên Desktop (HTML), tiện ích và đường lùi Tk giống nhau.

## 4. Thông tin nào hiện, thông tin nào ẩn

| Thông tin | WARN (đáng ngờ) | HIGH (nguy hiểm) | BLOCKED (danh sách đen) |
|-----------|:---------------:|:----------------:|:-----------------------:|
| Biểu tượng + nhãn mức | hiện (tam giác hổ phách, "Khoan đã! Link đáng ngờ") | hiện (bát giác đỏ, "Khoan đã! Link nguy hiểm") | hiện (ổ khóa đỏ đặc, "Đã chặn! Link lừa đảo") |
| Một câu kết luận | hiện | hiện | hiện ("Trang này nằm trong danh sách lừa đảo") |
| Một dòng nhắc việc cần làm | hiện ("Hãy cẩn thận trước khi mở link này.") | hiện ("Đừng đăng nhập hay nhập mã OTP vào trang này.") | hiện ("Đừng đăng nhập hay nhập bất cứ thông tin nào.") |
| Tên miền thật (đậm) + phần phụ (nhạt) | hiện | hiện, viền đỏ | hiện, viền đỏ đậm |
| Tô sáng phần giống tên ngân hàng, dạng punycode của tên miền Unicode, ký tự lạ gạch sóng | hiện khi có | hiện khi có | không áp dụng |
| "Trang chính thức của … là …" | hiện khi biết thương hiệu | hiện khi biết thương hiệu | không có |
| Dòng "Đang xác minh tuổi tên miền…" | hiện khi Tầng 3 còn chạy | hiện khi Tầng 3 còn chạy | không có (không cần Tầng 3) |
| Lý do chi tiết (tối đa 3 dòng, có biểu tượng) | **ẩn** trong "Xem vì sao" | **ẩn** trong "Xem vì sao" | **ẩn** trong "Xem vì sao" |
| Quay lại an toàn / Sao chép địa chỉ / Báo cho người gửi | hiện | hiện | hiện |
| "Vẫn mở link" + vòng đếm ngược | hiện, nhỏ, khóa 3 s (theo cài đặt) | hiện, nhỏ, khóa lâu hơn | hiện, nhỏ, khóa lâu nhất |
| Điểm số, tên tầng, câu lời khuyên dài, địa chỉ đầy đủ | **bỏ khỏi màn hình** (địa chỉ đầy đủ chỉ nằm trong clipboard khi bấm "Sao chép") | như WARN | như WARN |

Thời gian khóa vẫn theo `friction_seconds_for` (không đổi cơ chế): WARN thấp nhất, HIGH và BLOCKED cộng thêm.

## 5. Trước / sau

### Tiện ích trình duyệt (Zalo Web), chế độ tối

| Ca | Trước | Sau |
|----|-------|-----|
| WARN: tên miền lạ `khuyen-mai-hoan-tien.shop` | ![](ui/before/ext-warn.png) | ![](ui/after/ext-warn.png) |
| HIGH: giả Vietcombank + hối thúc `vcb-digibanks.top` | ![](ui/before/ext-high.png) | ![](ui/after/ext-high.png) |
| BLOCKED: nằm trong danh sách đen | ![](ui/before/ext-blocked.png) | ![](ui/after/ext-blocked.png) |
| IDN / đồng hình: `vietcombаnk.com` (chữ `а` Nga) | ![](ui/before/ext-idn.png) | ![](ui/after/ext-idn.png) |

### Chế độ sáng và cỡ điện thoại (chỉ có bản mới)

| WARN, sáng | BLOCKED, sáng | HIGH, 390 px |
|-----------|---------------|--------------|
| ![](ui/after/ext-warn-sang.png) | ![](ui/after/ext-blocked-sang.png) | ![](ui/after/ext-high-dien-thoai.png) |

### Desktop

| Trước (HTML cũ) | Sau (HTML mới, tiếng Việt) | Sau (tiếng Anh) |
|-----------------|----------------------------|-----------------|
| ![](ui/before/desktop-high.png) | ![](ui/after/desktop-high.png) | ![](ui/after/desktop-en-high.png) |

| WARN | BLOCKED | IDN |
|------|---------|-----|
| ![](ui/after/desktop-warn.png) | ![](ui/after/desktop-blocked.png) | ![](ui/after/desktop-idn.png) |

### Đường lùi Tkinter (khi giao diện HTML không chạy được)

| Trước | Sau (cùng bố cục, thanh tiến trình thay cho vòng đếm) |
|-------|-------------------------------------------------------|
| ![](ui/before/tk-high.png) | ![](ui/after/tk-high.png) |

Các ca còn lại của Tk: `ui/after/tk-warn.png`, `tk-blocked.png`, `tk-idn.png`.

### Cập nhật mượt khi Tầng 3 trả kết quả muộn

| Đang xác minh (WARN sơ bộ) | Tầng 3 xong, mức tăng lên HIGH | Mở "Xem vì sao" |
|----------------------------|-------------------------------|-----------------|
| ![](ui/after/desktop-dang-xac-minh.png) | ![](ui/after/desktop-da-cap-nhat.png) | ![](ui/after/desktop-xem-vi-sao.png) |

Đã đo vị trí các phần tử trước và sau khi `update()` chạy: nút "Quay lại an toàn", nút "Vẫn mở link" và thẻ tên miền không xê dịch pixel nào (câu kết luận và dòng trạng thái được giữ chỗ khi Tầng 3 còn chạy).

## 6. Quyết định thiết kế

**Một câu kết luận, chọn theo ưu tiên.** `chotto/plain.py` đặt cạnh `advisor.py`: bảng "mã tín hiệu → một câu ngắn". Thứ tự: danh sách đen, rồi sáu kịch bản tổ hợp **cùng nhóm mã và cùng thứ tự với `advisor.COMBOS`** (ví dụ giả danh + hối thúc = "Giả danh Vietcombank và hối thúc bạn"), rồi dấu hiệu riêng mạnh nhất, cuối cùng là câu mặc định theo mức. Các dấu hiệu yếu (đuôi tên miền, nhiều số, nhiều gạch ngang) không bao giờ tự làm câu kết luận mà chỉ xuất hiện ở "Xem vì sao". Một test kiểm tra mọi câu ≤ 12 từ và không chứa từ kỹ thuật.

**Tên miền là nhân vật chính.** Phần đăng ký (`xacthuc-tk.top`) đậm, tiền tố/đường dẫn nhạt. Tên ngân hàng đặt ở tên miền phụ (`vietcombank.com.vn.xacthuc-tk.top`) bị gạch đi vì là ngụy trang. Phần giống thương hiệu được tìm bằng từ khóa trong `rules.json` (khớp nguyên văn, rồi khoảng cách sửa ≤ 2 ký tự cho sai chính tả và ký tự đánh lừa). Tên miền Unicode hiện cả dạng punycode bên dưới, ký tự ngoài ASCII được gạch sóng.

**Mức độ không chỉ bằng màu.** Ba hình khác nhau (tam giác, bát giác, ổ khóa), nhãn chữ khác nhau và viền thẻ tên miền dày dần. Người mù màu phân biệt được ba mức.

**Phân cấp nút và đếm ngược.** "Quay lại an toàn" cao 58 px, rộng hết hàng, màu thương hiệu, nhận focus mặc định. "Vẫn mở link" cao 36 px, chữ nhỏ, viền mảnh, có vòng tròn cạn dần kèm số giây nhỏ trong vòng (cho trình đọc màn hình đọc "mở khóa sau N giây"). Cơ chế khóa có chủ ý không đổi: đếm theo `performance.now`, Python và service worker kiểm lại, tiện ích chỉ nhận cú bấm chuột thật.

**"Báo cho người gửi" soạn sẵn câu nhắn, không gửi gì.** Chỉ chép vào clipboard: "Link này có vẻ lừa đảo, bạn đừng bấm nhé: vcb-digibanks[.]top". Tên miền được viết dạng `[.]` để Zalo không biến nó thành link bấm được. Nút "Sao chép địa chỉ" chép địa chỉ đầy đủ (với tên miền Unicode là dạng punycode an toàn).

**Một nguồn cho cả ba nơi.**
- `chotto/shield.py` (Python) và `platforms/extension/src/view.js` (JS) cùng sinh cấu trúc `{headline, domain{registered, rest, ...}, reasonShort, details[], actions}`. `tools/gen_view_vectors.py` sinh `tests/data/view_vectors.json` (524 URL không an toàn); cả `tests/test_shield.py` lẫn `platforms/extension/tests/view.test.mjs` phải tái tạo đúng từng ký tự.
- Bảng chữ nằm ở `chotto/plain.py`; `tools/sync_extension_data.py` xuất sang `platforms/extension/data/plain.json` và `--check` phát hiện lệch.
- `chotto/web/shield.css` + `shield.js` là giao diện duy nhất. Desktop nạp trực tiếp, tiện ích nhận bản chép (`shield.js`) và CSS nhúng thành chuỗi (`shield-css.js`) từ cùng tool đồng bộ, vì content script không được lộ URL tài nguyên cho trang Zalo.
- Đường lùi Tk (`chotto/ui_shield.py`) đọc cùng `shield_view`, nên cùng chữ.

**Truy cập.** Tương phản đã kiểm bằng test (`tests/test_shield.py::ContrastTest`, đọc trực tiếp màu trong CSS): chữ thường ≥ 7,1:1 ở cả hai chế độ, biểu tượng ổ khóa trắng trên nền đỏ 4,6:1 (đạt AA). Esc luôn là "quay lại"; focus mặc định ở nút an toàn; vùng trạng thái dùng `aria-live`; `prefers-reduced-motion` tắt mọi chuyển động; cửa sổ cuộn được khi màn hình thấp.

**Sáng/tối.** Tiện ích theo hệ thống (`prefers-color-scheme`). Desktop giữ chế độ tối như yêu cầu (`data-theme="dark"`), bật chế độ sáng chỉ cần bỏ thuộc tính đó.

## 7. Điều cố ý không làm và hạn chế

- **Nút "Vẫn mở link" của tiện ích không nhận phím.** Đây là cơ chế chống bấm phản xạ có từ trước (Enter/Space không mở được; phải bấm chuột thật sau khi hết khóa). Người dùng chỉ dùng bàn phím vẫn thoát an toàn bằng Esc. Bản Desktop cho phép Enter sau khi hết khóa.
- **Tab "Kiểm tra link" trong cửa sổ ứng dụng Desktop** vẫn dùng `friction_view` cũ (hiển thị điểm và lý do kỹ thuật) vì đó là công cụ chẩn đoán, không phải màn hình cảnh báo. Có thể chuyển sang `shield_view` sau.
- **Tk** thay vòng đếm tròn bằng thanh tiến trình mảnh và không có biểu tượng cho từng dòng "Xem vì sao".
- **Bản tiếng Anh chỉ có ở Desktop** (tiện ích vốn chỉ có tiếng Việt). Bảng chữ tiếng Anh đã có test chống lẫn chữ Việt.
- Các ảnh chụp do trình duyệt Chromium không đầu (headless) tạo ra; cần kiểm bằng mắt trên máy thật, đặc biệt font Newsreader/Onest, độ co giãn ở DPI 125–150% và cửa sổ Desktop thật.

## 8. Cách chạy lại

```
python tools/sync_extension_data.py          # đồng bộ plain.json, shield.js, shield-css.js sang tiện ích
python tools/gen_view_vectors.py             # sinh lại vector khớp Python <-> JS
python -m unittest discover -s tests         # test Python
cd extension && npm test && npm run typecheck && npm run e2e
node e2e/ui-shots.mjs ../docs/ui/after ext-  # chụp ảnh tiện ích (CHROMIUM_PATH nếu cần)
python main.py --force "https://vcb-digibanks.top/xac-nhan"   # xem màn hình thật trên Desktop
```
