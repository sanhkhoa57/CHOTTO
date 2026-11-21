# Chế độ người giám hộ (Guardian mode)

Tính năng của **tiện ích trình duyệt CHOTTO** (Chrome/Edge, MV3) cho kịch bản *con cái bảo vệ bố mẹ lớn tuổi khỏi lừa đảo Zalo* (và ngược lại).
Nhánh làm việc: `guardian-mode` (tách từ `ui-redesign`). Không sửa engine chấm điểm và `chotto/data/rules.json`. Mọi thứ chạy **offline, không máy chủ**.

## 1. Mục tiêu

Khi Guardian bật, với link mức **HIGH** hoặc **BLOCKED** trên `chat.zalo.me`:

- nút "Vẫn mở" được thay bằng **"Xin phép người giám hộ"**;
- màn hình hiện **mã thử thách** (chữ + mã QR) gồm tên miền và một nonce ngẫu nhiên;
- người giám hộ dùng công cụ của mình (`tools/guardian.py` hoặc `guardian.html`) để tính **mã mở khóa 6 số**;
- người được bảo vệ nhập mã: link mở được, **chỉ đúng link đó, chỉ một lần**;
- mức **WARN** giữ hành vi cũ (đếm ngược rồi cho mở); Guardian tắt thì mọi thứ y như trước.

Ảnh chụp: `docs/guardian/` (`01-challenge.png`, `05-challenge-dark.png`, `02-wrong-code.png`, `03-locked.png`, `04-settings.png`).

## 2. Kiến trúc

```
 NGƯỜI ĐƯỢC BẢO VỆ (Standard User)                 NGƯỜI GIÁM HỘ (Administrator, thiết bị riêng)
 ─────────────────────────────────                 ─────────────────────────────────────────────
  chat.zalo.me: bấm link HIGH/BLOCKED
        │ content script (isolated world)
        ▼
  service worker: engine chấm điểm ─► cần Guardian?
        │   (cờ bật + khóa + bí mật đọc từ chrome.storage.managed,
        │    NGUỒN = registry HKLM do Admin ghi)
        ▼
  "Xin phép người giám hộ" ─► nonce = 40 bit ngẫu nhiên (WebCrypto)
        │   lưu thử thách {nonce, tên miền, hash(url), hạn 10', lượt}
        ▼
  Màn hình: tên miền + nonce K7QF-3MZD + QR           ──(đọc/quét, qua kênh người ĐƯỢC BẢO VỆ tự chọn)──►
                                                      guardian.py code <tên miền> <nonce>
                                                        1. chấm lại tên miền bằng engine Python
                                                        2. in CẢNH BÁO to, bắt gõ lại tên miền để xác nhận
                                                        3. mã = HOTP-truncate(HMAC-SHA256(secret,
                                                             "CHOTTO-GUARDIAN-v1|" + tên miền + "|" + nonce))
  nhập 6 số  ◄────────────────(mã mở khóa 6 số: 570 492)──────────────────────────────────────────────┘
        │
        ▼
  service worker: so mã với thử thách của CHÍNH link đó
     đúng  ─► XÓA thử thách ngay (một lần) ─► mở đúng URL đó
     sai   ─► lượt-1; hết 5 lượt ─► hủy; cứ 5 lần sai liên tiếp ─► khóa 30 giây → 2 phút → 10 phút
```

Thành phần:

| Tệp | Vai trò |
|-----|---------|
| `extension/src/guardian/codec.js` | HMAC-SHA256, SHA-256, Ed25519 verify, sinh nonce (đều của WebCrypto); base32/base64url, cắt bớt kiểu HOTP, so sánh thời gian hằng |
| `extension/src/guardian/guardian.js` | Cấu hình (managed + chính sách ký), thử thách, khóa, hết hạn, chống chỉnh giờ. Mọi phụ thuộc được tiêm vào nên kiểm thử bằng Node |
| `extension/src/guardian/managed_schema.json` | Lược đồ `chrome.storage.managed` (4 khóa: `guardian_enabled`, `guardian_public_key`, `guardian_secret`, `min_policy_version`) |
| `extension/src/background.js` | Ráp vào luồng cấp vé: thông điệp `guardian-request`, `guardian-submit`, `guardian-import`; vé Guardian không bao giờ nhận `decide: proceed` |
| `extension/src/ui/guardian-ui.js`, `guardian-css.js` | Màn hình xin phép (6 ô nhập, QR, thông báo, khóa tạm); QR dùng thư viện `qrcode-generator` (MIT, `src/vendor/`) |
| `tools/guardian.py` | Công cụ người giám hộ: `init`, `sign-policy`, `make-reg`, `code`, `make-html` |
| `tools/guardian.html` | Trang offline cùng chức năng `code` (mở trên điện thoại/máy khác) |
| `tools/gen_extension_key.py` | Ghim ID tiện ích (trường `key` trong manifest) |
| `tests/data/guardian_vectors.json` | Vector dùng chung Python ↔ JS (mã, base32, chữ ký Ed25519) |

## 3. Giả định tin cậy

1. Người được bảo vệ dùng tài khoản Windows **Standard User**; người giám hộ giữ tài khoản **Administrator**.
2. Chỉ Administrator ghi được `HKLM\SOFTWARE\Policies\…`. Mọi giá trị quan trọng của Guardian nằm ở đó.
3. Người giám hộ giữ thư mục khóa (`%APPDATA%\CHOTTO-Guardian`) và thiết bị tính mã ở nơi người được bảo vệ không với tới.
4. Người được bảo vệ *tự* chọn người giám hộ để liên lạc, qua kênh thứ hai (gọi điện số quen, gặp trực tiếp).

> **Giới hạn thẳng thắn:** nếu đối thủ có quyền Administrator thì mọi biện pháp ở user-space đều vượt được (sửa registry, gỡ tiện ích, đổi mã nguồn). Guardian không cố chống lại điều đó.

## 4. Mô hình đe dọa

Hai đối thủ khác nhau; mã nguồn và tài liệu tách riêng.

- **Đối thủ A, kẻ lừa đảo từ xa (chính):** gửi link, dụ bằng lời ("bấm xin phép đi", "đọc mã cho anh"), có thể dụ cả người giám hộ. **Không có quyền gì trên máy nạn nhân.**
- **Đối thủ B, chính người được bảo vệ có hiểu biết kỹ thuật** (ví dụ con tuổi teen muốn vượt): Standard User, đọc được file trong profile, cài được trình duyệt bản per-user, xóa được dữ liệu tiện ích, chỉnh được giờ hệ thống nếu được phép.

### 4.1 Đối thủ A

| # | Tấn công | Biện pháp | Còn rủi ro gì |
|---|----------|-----------|---------------|
| A1 | Dụ nạn nhân "đọc mã thử thách cho anh" rồi đòi "mã mở khóa" | Mã mở khóa cần bí mật HMAC mà A không có: có nonce cũng không tính được. Màn hình ghi rõ: *"Chỉ người giám hộ của bạn mới đưa mã này. Ai gọi điện xin mã thử thách là kẻ lừa đảo."* | Nạn nhân vẫn có thể bị dụ làm theo lời A theo cách khác (đọc mã cho A để A "giúp" gọi người giám hộ giả). Chỉ giảm được bằng giáo dục |
| A2 | Dụ người giám hộ cấp mã ("bố ơi con đang kẹt, cấp mã gấp") | `guardian.py code` chấm lại tên miền bằng engine, in **to** tên miền sẽ mở, cảnh báo HIGH/BLOCKED, bắt **gõ lại tên miền** để xác nhận; `guardian.html` bắt tick xác nhận đã gọi lại người thân | Là lỗi con người: người giám hộ vẫn có thể bị thuyết phục. Công cụ chỉ thêm ma sát và thông tin |
| A3 | Mã thử thách của link độc dùng để mở link khác | Mã gắn `tên miền + nonce`; thử thách còn gắn `SHA-256(url)`: mã của A không mở được B, kể cả cùng tên miền (nonce khác) | Không còn |
| A4 | Replay: dùng lại mã đã cấp | Thử thách bị xóa ngay khi dùng (một lần); mã không khớp thử thách mới (nonce mới) | Không còn |
| A5 | Chặn nạn nhân bằng link mà người giám hộ lỡ cho mở | Link được mở là link HIGH/BLOCKED đã được cho phép; sau đó là trang lừa đảo thật | **Rủi ro còn lại:** Guardian chỉ chặn *việc mở*; nó không bảo vệ nếu người giám hộ đã đồng ý |
| A6 | Nạn nhân copy link dán vào thanh địa chỉ, hoặc mở link ở Zalo Desktop/điện thoại | Không có (tiện ích chỉ thấy cú bấm trên `chat.zalo.me`) | **Vượt được.** Giảm thiểu: giáo dục; về sau bản Desktop (mục 9) |

### 4.2 Đối thủ B

| # | Tấn công | Biện pháp | Còn rủi ro gì |
|---|----------|-----------|---------------|
| B1 | Tắt Guardian bằng cách sửa `chrome.storage.local`/file profile | Cờ bật, khóa công khai, bí mật, `min_policy_version` **chỉ đọc từ managed storage** (HKLM). `storage.local` không bao giờ được tin cho các giá trị này (test: `guardian.test.mjs`) | Không còn với cách này |
| B2 | Thay chính sách mở rộng bằng bản "lỏng" tự viết | Chính sách chỉ được nhận khi chữ ký Ed25519 đúng theo khóa trong managed storage. Sai/thiếu/hỏng → **fail-closed** | Không còn |
| B3 | Hạ cấp: dùng lại bản chính sách cũ *có chữ ký hợp lệ* nhưng lỏng hơn | `version ≥ min_policy_version` (giá trị `min_policy_version` nằm ở HKLM) | Admin phải nâng `min_policy_version` mỗi khi *siết* chính sách (làm bằng `make-reg --min-policy-version`) |
| B4 | Đoán mã 6 số | Tối đa 5 lượt/thử thách; cứ 5 lần sai liên tiếp trên toàn tiện ích khóa 30 s → 2 phút → 10 phút, khóa còn **hủy mọi thử thách**; bộ đếm toàn cục nên đổi thử thách không reset được. Xác suất ≈ 10⁻⁶ mỗi lượt | Xem B6: nếu B đọc được bí mật thì không cần đoán |
| B5 | Chỉnh giờ hệ thống để kéo dài thử thách | `last_seen`: lùi quá 5 phút → hủy mọi thử thách + ghi cảnh báo (hiện ở trang cài đặt). Khởi động lại trình duyệt/service worker mất `storage.session` → hủy thử thách | Lùi ≤ 5 phút kéo dài được ≤ 5 phút; **tiến** giờ làm hết khóa sớm hơn (khóa tính theo giờ hệ thống) |
| B6 | **Đọc bí mật HMAC** rồi tự tính mã | Không có biện pháp trong thiết kế hiện tại | **Vượt được** (xem mục 6). Registry `Policies` thường đọc được bởi Standard User (trình duyệt chạy dưới quyền user cũng phải đọc nó); `storage.managed` đọc được qua DevTools của service worker |
| B7 | Sửa mã tiện ích khi load unpacked (thư mục nằm trong quyền ghi của B) | Không có | **Vượt được ngay.** Chế độ demo (load unpacked) KHÔNG chống được B. Chỉ tiện ích đóng gói/ép cài (CRX ký, trong thư mục profile được trình duyệt kiểm tra toàn vẹn) mới cản được việc này |
| B8 | Mở DevTools của service worker để vá `chrome.storage.managed.get` (đúng cách test e2e giả lập) | Policy chặn DevTools (`.reg` làm cứng) | Phụ thuộc trình duyệt/phiên bản; xem 7.4 và các dòng *chưa kiểm chứng* |
| B9 | Xóa dữ liệu tiện ích / đặt lại | Cờ bật vẫn ở managed → vẫn bật, dùng mặc định nghiêm nhất. Thử thách bị mất theo bộ đếm nên không lợi gì | Không còn |
| B10 | Tạo khóa **HKCU**`\SOFTWARE\Policies\…\3rdparty\…` để đè giá trị | Tài liệu Chromium nói trình duyệt đọc cả HKCU; `make-reg` ghi cả 4 khóa ở HKLM nên (theo quy tắc chung "machine ưu tiên hơn user") HKLM thắng | **Chưa kiểm chứng** thứ tự ưu tiên cho `3rdparty` trên máy bạn. Hãy thử: tạo khóa HKCU với `guardian_enabled=0` rồi xem `chrome://policy` |
| B11 | Cài trình duyệt khác bản per-user (Chrome portable, Firefox…), hoặc đổi trình duyệt mặc định | Giảm thiểu: **AppLocker** (bản Windows Pro/Enterprise) chặn chạy file `.exe` trong `%LOCALAPPDATA%`/`Downloads`; giả định Standard User (không ghi được Program Files) | **Vượt được** nếu không có AppLocker |
| B12 | Gỡ/tắt tiện ích tại `chrome://extensions` | Chỉ ngăn được khi tiện ích bị ép cài (`ExtensionInstallForcelist`) | Xem 7.5: ép cài ổn định chỉ với tiện ích Chrome Web Store |
| B13 | Mở link từ Zalo Desktop/điện thoại | Không có | **Vượt được** (cùng A6) |
| B14 | Admin sửa registry | — | Ngoài mô hình (mục 3) |

### 4.3 Các đường vượt còn lại (tổng hợp)

Cài trình duyệt khác bản per-user · mở link từ Zalo Desktop/điện thoại/dán vào thanh địa chỉ · gỡ tiện ích nếu không bị ép cài · sửa mã tiện ích khi load unpacked · đọc bí mật HMAC · Admin sửa registry.
Giảm thiểu: AppLocker (bản Pro), bản Desktop CHOTTO (mục 9), giả định Standard User, tiện ích đóng gói + ép cài.

**Bản Desktop (Python) nằm ngoài phạm vi lần này:** Standard User đổi được trình duyệt mặc định (và handler `http/https`) bằng cài đặt của chính mình, nên chốt chặn của Desktop bị vượt dễ dàng khi đối thủ là B.

## 5. Lựa chọn mật mã và lý do

Không tự viết thuật toán mật mã: HMAC-SHA256, SHA-256, Ed25519, số ngẫu nhiên đều từ WebCrypto (JS) và `hmac`/`hashlib`/`cryptography` (Python). Phần tự viết chỉ là "keo": base32/base64url, cắt bớt HOTP, so sánh thời gian hằng.

**Mã mở khóa.** `HMAC-SHA256(secret, "CHOTTO-GUARDIAN-v1|" + tên miền + "|" + nonce)`, rồi cắt bớt kiểu HOTP (RFC 4226 §5.3: offset = nibble thấp của byte cuối, lấy 31 bit, `mod 10⁶`). Vector chung `tests/data/guardian_vectors.json`; cả Python và JS phải tái tạo từng mã.

**Vì sao HMAC + nonce chứ không TOTP thuần?**
- TOTP là *mã theo thời gian*: một mã hợp lệ cho **mọi** link trong cả cửa sổ 30 s. Kẻ lừa đảo dụ nạn nhân đọc mã vừa nhận có thể dùng nó cho link bất kỳ; mã cũng không gắn với trang cần mở.
- Challenge–response gắn mã với `tên miền + nonce` của **một** thử thách: mã không dùng cho tên miền khác, thử thách khác, hay lần khác.
- TOTP đòi hai đồng hồ lệch nhau không quá một cửa sổ; thử thách thì không phụ thuộc đồng hồ của người giám hộ (đồng hồ chỉ dùng để tính hạn ở phía tiện ích).

**Nonce:** 5 byte từ `crypto.getRandomValues` (40 bit), hiển thị base32 8 ký tự `K7QF-3MZD` (không có `0/1/8/9` dễ nhầm).

**Vì sao không cần danh sách "mã đã dùng"?** Mã chỉ khớp với thử thách *đang chờ* của *chính link đó*, và thử thách bị **xóa ngay** khi dùng đúng (hoặc khi hết hạn/hủy). Dùng lại mã đã dùng nghĩa là gửi mã cho một thử thách không còn tồn tại (`gone`), hoặc cho thử thách mới có nonce mới (mã cũ sai). Một danh sách mã đã dùng chỉ thêm trạng thái cần giữ (và có thể bị xóa) mà không chặn thêm cuộc tấn công nào.

**Vì sao fail-closed?** Chính sách mở rộng đi qua `storage.local` — kênh mà đối thủ B ghi được. Nếu chính sách ký sai/thiếu/hỏng được xử lý bằng "giữ chính sách cũ" thì (a) có thể không còn chính sách cũ, (b) kẻ tấn công chỉ cần làm hỏng bản mới để buộc dùng bản cũ lỏng. Vì cờ bật nằm trong managed (OS bảo vệ) nên Guardian vẫn bật; không có chính sách hợp lệ thì dùng **mặc định nghiêm nhất: HIGH và BLOCKED đều cần mã** (không có danh sách cho phép). Cấu hình managed hỏng (bật nhưng thiếu bí mật) cũng fail-closed: chặn và không ai mở khóa được cho tới khi sửa.

**Vì sao Ed25519 + `min_policy_version`?** Chữ ký xác thực chính sách đi qua kênh không đặc quyền (người giám hộ sửa danh sách cho phép mà không cần Administrator). Chữ ký đơn thuần chưa đủ: bản cũ vẫn hợp lệ mãi, nên cần số phiên bản và mức sàn `min_policy_version` nằm trong HKLM (chống rollback). Phần *trong managed storage* đã được hệ điều hành bảo vệ ghi nên **không cần ký**. Ký payload là *chuỗi JSON nguyên văn* (không phải đối tượng) để khỏi phụ thuộc vào cách chuẩn hóa JSON; thông điệp ký có tiền tố `CHOTTO-GUARDIAN-POLICY-v1\n` để tách miền với mọi chữ ký khác.

**Quy tắc chính sách:** `BLOCKED` luôn cần mã (chính sách không nới được); danh sách "luôn cho phép" không áp dụng cho `BLOCKED`; `require_levels` ⊆ {WARN, HIGH, BLOCKED} (thêm WARN nghĩa là siết hơn); hạn thử thách 60–3600 giây.

**Ed25519 trong trình duyệt:** cần WebCrypto Ed25519. Nếu trình duyệt không hỗ trợ thì xác minh thất bại → chính sách bị bỏ → mặc định nghiêm nhất (vẫn an toàn, chỉ mất tính năng chính sách mở rộng). Bản Chromium dùng để kiểm thử (156) hỗ trợ. `minimum_chrome_version` của manifest vẫn là 111, không đổi.

## 6. Giới hạn trung thực

- **HMAC đối xứng an toàn trước đối thủ A, không an toàn tuyệt đối trước đối thủ B.** Bí mật nằm ở máy người được bảo vệ (đọc từ managed storage; registry `Policies` thường đọc được bởi Standard User, dữ liệu profile cũng đọc được). B rành kỹ thuật tự tính được mã. Không có cách vá nào chỉ bằng đối xứng: cái tiện ích dùng để *kiểm* mã cũng là cái đủ để *tính* mã.
- Chế độ demo (load unpacked) không chống được B (B7).
- Tiện ích chỉ thấy cú bấm trên `chat.zalo.me`; dán link vào thanh địa chỉ, Zalo Desktop, điện thoại, trình duyệt khác đều không qua Guardian.
- Nếu managed storage *không được publish* (sai kiểu giá trị so với lược đồ, thiếu schema, chưa nạp lại chính sách) thì Guardian **tắt âm thầm** (hành vi cũ). Vì vậy bước demo yêu cầu kiểm tra trang Cài đặt của tiện ích phải ghi "Đang bật bởi chính sách quản lý" và `chrome://policy`.
- **Chấm lại chỉ theo tên miền.** `guardian.py code` chỉ thấy tên miền (đúng yêu cầu), không thấy đường dẫn/cổng/tham số của link, nên có thể chấm *thấp hơn* tiện ích (ví dụ IP trần: WARN so với HIGH của cả link). Công cụ in chú thích này; nó không thay được việc tự hỏi người thân.
- Khóa tạm tính theo giờ hệ thống: tiến giờ làm hết khóa sớm.
- Ghi nhật ký quyết định (nếu bật) ghi `proceed` cho cả link mở bằng mã; không ghi mã hay nonce.
- Người giám hộ bị lừa là rủi ro con người; công cụ chỉ thêm ma sát và thông tin.

## 7. Hướng dẫn cài cho demo (từng bước)

Yêu cầu: Windows, Chrome (hoặc Edge), Python 3.11+ với `pip install -r requirements.txt` (gói `cryptography` cho Ed25519), tài khoản Administrator để chạy `.reg`.
**Không có bước nào tự ghi registry** — các lệnh dưới đây do bạn chạy.

### 7.1 Sinh khóa (người giám hộ)

```powershell
python tools\guardian.py init
```

Tạo `%APPDATA%\CHOTTO-Guardian\keys.json` (khóa Ed25519 + bí mật HMAC; ngoài repo, chỉ chủ sở hữu đọc được). Công cụ từ chối ghi vào trong repo; `*.pem`, `*.key`, `CHOTTO-Guardian/` nằm trong `.gitignore`. **Sao lưu thư mục này**.

ID tiện ích đã ghim sẵn bằng trường `key` trong `extension/manifest.json` (khóa bí mật của cặp khóa này nằm ngoài repo, `tools/gen_extension_key.py`): **`khbkfclofacncmkcgjndadchgohkaflg`**, nên registry trỏ đúng tiện ích khi load unpacked.

### 7.2 (Tùy chọn) Chính sách ký

```powershell
# policy.json:  {"allow_domains": ["vietcombank.com.vn"], "require_levels": ["HIGH"], "challenge_ttl_sec": 600}
python tools\guardian.py sign-policy policy.json      # -> policy.signed.json, version tự tăng
```

Dán nội dung `policy.signed.json` vào trang Cài đặt của tiện ích, mục "Chế độ người giám hộ" (chỉ nhận nếu chữ ký đúng và version ≥ mức tối thiểu).

### 7.3 Tạo file .reg và chạy bằng Administrator

```powershell
python tools\guardian.py make-reg --browser chrome     # hoặc --browser edge
```

Tạo 3 file trong thư mục người giám hộ (chỉ tạo, **không áp dụng**):

| File | Nội dung |
|------|----------|
| `chotto-guardian-<trình duyệt>.reg` | Bật Guardian: `guardian_enabled`, `guardian_public_key`, `guardian_secret`, `min_policy_version`. **Chứa bí mật.** |
| `chotto-guardian-<trình duyệt>-remove.reg` | Gỡ bỏ: xóa khóa chính sách của tiện ích và các giá trị làm cứng |
| `chotto-guardian-<trình duyệt>-hardening.reg` | Làm cứng gợi ý (xem 7.4). **Không dùng cho demo load unpacked** |

Chạy: chuột phải `chotto-guardian-chrome.reg` → *Merge* (hoặc PowerShell chạy bằng "Run as administrator": `reg import "<đường dẫn>"`). Đường dẫn registry:

- Chrome: `HKLM\SOFTWARE\Policies\Google\Chrome\3rdparty\extensions\<id>\policy` (theo tài liệu Chromium *Configuring policy for extensions*, trang này cũng nói có thể dùng HKCU thay HKLM).
- Edge: `HKLM\SOFTWARE\Policies\Microsoft\Edge\3rdparty\extensions\<id>\policy` — **chưa kiểm chứng**: chỉ thấy trong một trả lời cộng đồng Microsoft Q&A, không phải tài liệu chính thức. Tự kiểm chứng trên máy bạn.

Kiểu giá trị: `guardian_enabled`, `min_policy_version` ghi `REG_DWORD`; hai khóa kia `REG_SZ`. Trang Chromium *không nêu* quy tắc kiểu cho `3rdparty` nên đây là **chưa kiểm chứng**; xem bước kiểm tra dưới. Nếu `guardian_enabled` không hiện ở `chrome://policy`, đổi `type` trong `managed_schema.json` sang `string` và ghi `REG_SZ "1"` (mã JS chấp nhận `true`, `1`, `"1"`, `"true"`).

Sau khi merge: đóng hẳn trình duyệt, mở lại, vào `chrome://policy` (hoặc `edge://policy`), bấm *Reload policies*.

### 7.4 Policy làm cứng (đã tạo, chưa áp dụng)

`-hardening.reg` đặt (trong `HKLM\SOFTWARE\Policies\Google\Chrome` hoặc `...\Microsoft\Edge`):

| Policy | Giá trị | Trình duyệt | Mức kiểm chứng |
|--------|---------|-------------|----------------|
| `IncognitoModeAvailability` | `1` (tắt chế độ ẩn danh) | Chrome | Một kết quả tìm kiếm trích trang trợ giúp của Google nói đặt `1` thì tắt Incognito; **chưa đọc trực tiếp trang chính sách** |
| `InPrivateModeAvailability` | `1` (tắt InPrivate) | Edge | Đã đọc Microsoft Learn: `0` bật, `1` tắt, `2` bắt buộc; `REG_DWORD`, `SOFTWARE\Policies\Microsoft\Edge` |
| `DeveloperToolsAvailability` | `2` (không cho DevTools) | Edge | Đã đọc Microsoft Learn: `0` chặn DevTools *chỉ trên tiện ích cài bằng policy*, `1` cho phép, `2` cấm hoàn toàn |
| | | Chrome | **Chưa kiểm chứng** (trang chính sách của Google nạp bằng JS, không đọc được); tên/giá trị suy ra từ Edge vì cùng nền Chromium |
| `ExtensionDeveloperModeSettings` (để dạng **chú thích**) | `1` (cấm chế độ nhà phát triển) | Edge ≥ 128 | Đã đọc Microsoft Learn; trang không nói thẳng "Load unpacked" bị chặn |
| | | Chrome | **Chưa kiểm chứng** |

Cảnh báo: `DeveloperToolsAvailability=2` tắt cả DevTools của bạn; `ExtensionDeveloperModeSettings=1` cấm "Load unpacked" và có thể tắt tiện ích unpacked đang chạy (**chưa kiểm chứng**). Vì vậy: không áp dụng cho demo load unpacked; dòng sau được để dạng chú thích.

### 7.5 Ép cài và chống gỡ

Demo **không** cần `ExtensionInstallForcelist`: load unpacked + managed storage qua registry là đủ chạy Guardian. Ép cài và chống gỡ qua `ExtensionInstallForcelist` trên **Chrome ở máy không vào domain** chỉ ổn định với tiện ích đến từ Chrome Web Store (tôi không đọc được trang chính sách chính thức để xác nhận; đây là điều thường được ghi nhận, không phải khẳng định đã kiểm chứng). **Edge có thể dễ hơn nhưng phải tự kiểm chứng trên máy bạn**; không khẳng định ở đây.

### 7.6 Load unpacked

`chrome://extensions` → bật *Developer mode* → *Load unpacked* → chọn thư mục `extension/`. Kiểm tra ID bằng `khbkfclofacncmkcgjndadchgohkaflg`. Mở trang Cài đặt của tiện ích (bấm biểu tượng): mục **Chế độ người giám hộ** phải ghi *"Đang bật bởi chính sách quản lý (managed storage)"*. Nếu ghi "Đang tắt", managed storage chưa được publish (xem lại 7.3).

### 7.7 Thử

1. Mở `https://chat.zalo.me/` và nhắn cho chính mình link thử `http://192.168.1.10:8080/tra-cuu-phat-nguoi` (IP riêng, tiện ích chấm HIGH vì cả cổng và đường dẫn, không ra Internet). Bấm vào link.
2. Bấm **Xin phép người giám hộ**: thấy tên miền, mã thử thách (ví dụ `K7QF-3MZD`) và QR.
3. Người giám hộ chạy: `python tools\guardian.py code 192.168.1.10 K7QF-3MZD` (hoặc dán nguyên nội dung QR). Công cụ hiện cảnh báo, bắt gõ lại tên miền, rồi in mã 6 số. (Công cụ chỉ thấy *tên miền*: với IP nó chấm WARN chứ không phải HIGH, vì thiếu cổng/đường dẫn mà tiện ích đã chấm. Xem mục 6.)
4. Nhập 6 số: link mở trong tab mới. Thử nhập sai 5 lần để thấy khóa; link mức WARN vẫn là "đếm ngược rồi mở".
5. Trên điện thoại: `python tools\guardian.py make-html` tạo `guardian-app.html` (có nhúng bí mật; chép sang thiết bị của bạn, **không** đưa vào repo).
6. Gỡ: chạy `chotto-guardian-<trình duyệt>-remove.reg` bằng Administrator, rồi gỡ tiện ích.

Muốn thử đúng vai đối thủ B: chạy trình duyệt bằng tài khoản Standard User. Với demo load unpacked, bạn sẽ thấy B sửa được mã nguồn (B7): đó là giới hạn đã nêu ở trên.

## 8. Kiểm thử

Không gọi mạng thật.

| Nhóm | Lệnh | Nội dung chính |
|------|------|----------------|
| Node (`extension/tests/guardian.test.mjs`) | `cd extension && npm test` | mã đúng mở đúng link; mã đúng của tên miền khác bị từ chối; dùng lại mã bị từ chối; quá 5 lần sai → hủy + khóa 30 s/2 phút/10 phút; hết hạn; lùi giờ → hủy; khởi động lại/xóa kho → mất thử thách; chính sách sai chữ ký/thiếu/hỏng/version thấp hơn min → fail-closed; managed thiếu → hành vi cũ; vector HMAC/base32/Ed25519 khớp Python |
| Python (`tests/test_guardian.py`) | `python -m unittest discover -s tests` | mã khớp vector chung và RFC 4226; ký/xác minh/rollback; xuất `.reg` (đường dẫn Chrome/Edge, DWORD, UTF-16, không chứa bí mật ở file gỡ/làm cứng); từ chối ghi trong repo; chấm lại bằng engine; xác nhận tương tác |
| E2E (`extension/e2e/guardian.test.mjs`) | `cd extension && npm run e2e` | Chromium thật + managed storage **giả lập** (ghi đè `chrome.storage.managed.get` trong service worker, không đụng registry); mã tính bằng `tools/guardian.py` thật; mã đúng mở link, sai 5 lần bị khóa, WARN/Guardian tắt giữ hành vi cũ, trang cài đặt chỉ đọc + nhận chính sách ký. Cần Chromium của Playwright (`npx playwright install chromium`; đặt `CHROMIUM_PATH` nếu phiên bản không khớp) |

## 9. Hướng phát triển

1. **Chữ ký bất đối xứng cho mã** (chống B đọc bí mật): người giám hộ *ký* Ed25519 lên thử thách; chữ ký 64 byte chuyển ngược về qua mã QR (webcam) hoặc file. Tiện ích chỉ giữ khóa công khai nên không thể tự tính mã. Tốn kém UX (64 byte ≈ 86 ký tự base64), chỉ mô tả, chưa làm.
2. **Ép cài qua Chrome Web Store** (`ExtensionInstallForcelist`) để chống gỡ và chống sửa mã.
3. **Bản Desktop**: handler `http/https` của Windows bị Standard User đổi được; cần AppLocker hoặc tách thành dịch vụ.
4. **Thông báo từ xa**: người giám hộ nhận cảnh báo khi người thân gặp link nguy hiểm (đòi hỏi kênh mạng, phá vỡ tính offline: cân nhắc).
5. Nhận thử thách bằng quét QR trên điện thoại của người giám hộ (đã có nội dung QR; còn thiếu ứng dụng quét).

## 10. Quyết định kỹ thuật (làm khác hoặc thêm so với yêu cầu)

- **Bộ đếm sai toàn cục.** Yêu cầu nói "5 lần/thử thách" và "khóa tăng dần toàn tiện ích". Nếu chỉ đếm theo thử thách, B đổi thử thách (bấm lại link) là có 5 lượt mới. Nên: mỗi thử thách vẫn tối đa 5 lượt, **cộng thêm** bộ đếm sai liên tiếp toàn cục (không reset khi đổi thử thách; reset khi mở đúng hoặc sau 1 giờ yên). Cứ 5 lần sai liên tiếp → khóa 30 s, 2 phút, 10 phút và **hủy mọi thử thách**.
- **Thử thách phát *lười*** khi bấm "Xin phép" (không phát lúc hiện cảnh báo): nonce chỉ tồn tại khi thật sự được hỏi, đồng hồ 10 phút chỉ chạy từ lúc đó.
- **Lưu thử thách ở `storage.local` có kèm `bootId`** (so với `storage.session`): bộ đếm và thử thách cùng một kho, nên xóa bộ đếm thì thử thách mất theo (như yêu cầu), nhưng vẫn hủy khi trình duyệt khởi động lại vì `bootId` ở `storage.session` mất.
- **`BLOCKED` luôn cần mã.** Chính sách ký không nới được `BLOCKED` và danh sách "luôn cho phép" không áp dụng cho `BLOCKED` (danh sách đen thắng).
- **Managed đọc lỗi** (ví dụ chưa có schema): dùng bản đọc tốt gần nhất trong bộ nhớ service worker; nếu chưa từng đọc được thì coi như Guardian tắt (khớp yêu cầu "managed thiếu → hành vi cũ"). Hệ quả: lần khởi động đầu tiên mà managed lỗi thì Guardian tắt (đã nêu ở mục 6).
- **`content.js` dự phòng:** khi không liên lạc được service worker, màn hình dự phòng cho phép "vẫn mở" sau 5 giây; nếu `chrome.storage.managed` cho thấy Guardian bật thì ẩn hẳn nút đó (fail-closed). Nếu chính content script bị vô hiệu (ngữ cảnh tiện ích bị hủy) thì không còn gì chạy, đây là giới hạn B12.
- **Tiện ích chỉ chấm domain đăng ký ở dạng ASCII (punycode).** Công cụ giám hộ chuẩn hóa tên miền Unicode sang punycode (IDNA); màn hình hiện dạng ASCII để người giám hộ và công cụ thấy cùng một chuỗi.
- **QR dùng thư viện đã kiểm chứng** `qrcode-generator` 1.4.4 (MIT) chép vào `src/vendor/` (không sửa), thay vì tự viết bộ mã hóa QR.
- **`guardian.html` không chấm lại được tên miền** (không có engine Python trong trình duyệt): thay bằng cảnh báo "CHOTTO chỉ hiện thử thách khi đã chấm nguy hiểm", bắt tick xác nhận đã gọi lại người thân, và gợi ý dùng `guardian.py code` nếu có máy tính.
- **Ba file `.reg` thay vì hai:** thêm file làm cứng tách riêng vì hai policy làm cứng phá vỡ demo load unpacked.
- **Khóa ghim ID bằng RSA-2048** theo cách Chrome tính ID (`SHA-256` của khóa công khai → `a–p`); `key` bị bỏ khỏi bản Firefox.
- **`ExtensionInstallForcelist` không được ghi vào `.reg`** vì chưa kiểm chứng được; chỉ nêu trong tài liệu.
