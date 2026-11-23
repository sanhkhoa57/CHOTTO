# Thử nghiệm khả dụng: Guardian mode cho người lớn tuổi

Tài liệu kịch bản để **bạn** tổ chức và ghi kết quả. Các bảng kết quả để trống. Chưa có số liệu nào trong tài liệu này; đừng trích số nào từ đây vào báo cáo trước khi đã chạy thử nghiệm.

## 1. Mục tiêu

Kiểm tra xem bản làm lại (hai màn hình, lời nhắn tự chép, một ô nhập số, trang người giám hộ) có giúp người lớn tuổi **hoàn thành nhanh hơn, ít sai hơn, ít phải hỏi trợ giúp hơn và hài lòng hơn** bản cũ (mã thử thách đọc qua điện thoại + 6 ô nhập) hay không. Câu hỏi nghiên cứu:

1. Người tham gia có hoàn thành việc "nhờ người giám hộ → mở được / không mở" mà không cần trợ giúp không?
2. Họ có hiểu vì sao link bị chặn và việc cần làm (đóng, hoặc nhờ người giám hộ) không?
3. Bản mới có giảm thời gian, số lần sai và số lần hỏi trợ giúp so với bản cũ không?

## 2. Hai phiên bản so sánh

| Ký hiệu | Phiên bản | Cách dựng |
|---------|-----------|-----------|
| **A (cũ)** | commit `d07e28f` (trước lần làm lại UX): màn hình chặn nhiều lựa chọn, mã thử thách dạng `WIUJ-GXRR` + QR, 6 ô nhập | `git worktree add ../chotto-ban-cu d07e28f`, nạp `../chotto-ban-cu/extension` (Load unpacked). Người giám hộ dùng `python tools\guardian.py code <tên miền> <mã thử thách>` (hoặc `guardian.html`) |
| **B (mới)** | nhánh `guardian-mode` hiện tại | nạp thư mục `platforms/extension/` của kho này. Người giám hộ dùng trang `guardian/index.html` (đã cài bí mật thử) trên điện thoại |

Cả hai bản dùng **cùng ID tiện ích** (khóa ghim trong manifest) nên chỉ nạp **một bản mỗi lần**: gỡ bản này rồi nạp bản kia giữa hai phiên. Cả hai cần managed storage để Guardian bật (xem `docs/GUARDIAN-MODE.md` mục 7): dùng **máy thử riêng** hoặc hồ sơ trình duyệt riêng, tạo `.reg` bằng khóa/bí mật **thử** (thư mục `--dir` riêng, không phải khóa thật của bạn), và gỡ bằng file `-remove.reg` sau thử nghiệm. Với bản B cần host hoặc chạy trang `guardian/` (ví dụ `python -m http.server` trong thư mục gốc kho) và `make-reg --page-url http://localhost:PORT/guardian/` (cho phép `http://localhost` để thử).

**Không cần Zalo thật.** Để tạo màn hình chặn không phải dùng tài khoản thật, mở trang cảnh báo của chính tiện ích: `chrome-extension://khbkfclofacncmkcgjndadchgohkaflg/src/ui/warn.html?u=http%3A%2F%2F192.168.1.10%3A8080%2Ftra-cuu-phat-nguoi`. Đây là link tới một địa chỉ mạng nội bộ (không ra Internet, không phải trang lừa đảo thật) và được chấm mức HIGH, nên Guardian yêu cầu người giám hộ. Dùng cùng một link cho mọi người tham gia ở cả hai bản.

Kênh trò chuyện giữa người tham gia và người giám hộ: hai **tài khoản thử** (hoặc một ứng dụng nhắn tin bất kỳ với hai tài khoản mới tạo cho thử nghiệm), hoặc dán lời nhắn vào một tệp ghi chú rồi người điều phối chuyển tay. **Không dùng tài khoản Zalo thật** của người tham gia hay của bạn.

## 3. Người tham gia

- **3–5 người** từ 60 tuổi trở lên, đang dùng điện thoại/máy tính và biết nhắn tin; không cần rành công nghệ (nên có cả người ít dùng máy tính). Ghi: mã người tham gia (P1, P2…), nhóm tuổi, mức quen dùng máy tính (1–5), có dùng Zalo không.
- Vai **người giám hộ** do người điều phối (hoặc một người thân thật sự đồng ý) đảm nhận ở phòng/thiết bị khác; người giám hộ đã được hướng dẫn trước cách dùng cả hai công cụ và **không gợi ý** cho người tham gia trừ khi họ hỏi.
- Cân đối thứ tự: nửa số người làm bản A trước rồi B, nửa còn lại B trước rồi A (giảm hiệu ứng học). Nghỉ ngắn giữa hai bản.

## 4. Nhiệm vụ (mỗi bản đều làm cả hai)

Đọc cho người tham gia (kịch bản, không dùng từ kỹ thuật): *"Bạn đang đọc tin nhắn thì thấy một đường link. Hãy thử mở nó. Nếu máy báo gì, bạn cứ làm theo cách bạn thấy hợp lý. Mình sẽ không giúp trừ khi bạn nhờ. Bạn nói to điều bạn đang nghĩ nhé."*

| # | Nhiệm vụ | Hoàn thành khi |
|---|----------|----------------|
| T1 | Gặp link nguy hiểm → **nhờ người giám hộ** → người giám hộ **cho mở** → link mở được | Người tham gia nhập đúng mã và link mở |
| T2 | Gặp link nguy hiểm → nhờ người giám hộ → người giám hộ **không cho mở** | Người tham gia hiểu là không mở và đóng màn hình (không cố mở bằng cách khác) |

Người giám hộ chỉ trả lời khi nhận được yêu cầu. Giới hạn 10 phút mỗi nhiệm vụ; quá thì ghi "không hoàn thành".

## 5. Đo gì và ghi thế nào

Với mỗi người, mỗi bản, mỗi nhiệm vụ:

- **Thời gian hoàn thành (giây):** từ lúc màn hình chặn hiện đến lúc hoàn thành (T1: link mở; T2: màn hình đóng). Bấm đồng hồ; **không tính** thời gian chờ người giám hộ trả lời (ghi riêng "chờ người giám hộ").
- **Số lần sai:** gõ sai mã, bấm nhầm nút (ví dụ bấm Đóng khi định nhờ), dán nhầm chỗ, đọc/gõ nhầm ký tự trong mã.
- **Số lần phải hỏi trợ giúp:** người tham gia hỏi người điều phối ("giờ làm gì?", "cái này là gì?"). Mỗi lần hỏi tính một lần, kể cả khi người điều phối không trả lời nội dung.
- **Hoàn thành:** có / không / có trợ giúp.
- **Quan sát và trích dẫn:** chỗ ngập ngừng, câu nói to, từ ngữ không hiểu.
- **SUS** sau mỗi bản (mục 6).

### Bảng ghi kết quả (để trống)

**Bản A (cũ: `d07e28f`)**

| Mã | Nhiệm vụ | Thời gian (s) | Chờ người giám hộ (s) | Số lần sai | Số lần hỏi trợ giúp | Hoàn thành (có/không/có trợ giúp) | Ghi chú |
|----|----------|---------------|-----------------------|-----------|----------------------|----------------------------------|---------|
| P1 | T1 | | | | | | |
| P1 | T2 | | | | | | |
| P2 | T1 | | | | | | |
| P2 | T2 | | | | | | |
| P3 | T1 | | | | | | |
| P3 | T2 | | | | | | |
| P4 | T1 | | | | | | |
| P4 | T2 | | | | | | |
| P5 | T1 | | | | | | |
| P5 | T2 | | | | | | |

**Bản B (mới)**

| Mã | Nhiệm vụ | Thời gian (s) | Chờ người giám hộ (s) | Số lần sai | Số lần hỏi trợ giúp | Hoàn thành (có/không/có trợ giúp) | Ghi chú |
|----|----------|---------------|-----------------------|-----------|----------------------|----------------------------------|---------|
| P1 | T1 | | | | | | |
| P1 | T2 | | | | | | |
| P2 | T1 | | | | | | |
| P2 | T2 | | | | | | |
| P3 | T1 | | | | | | |
| P3 | T2 | | | | | | |
| P4 | T1 | | | | | | |
| P4 | T2 | | | | | | |
| P5 | T1 | | | | | | |
| P5 | T2 | | | | | | |

**Tổng hợp (điền sau)**

| Chỉ số | Bản A | Bản B |
|--------|-------|-------|
| Số người hoàn thành T1 không cần trợ giúp | | |
| Số người hoàn thành T2 không cần trợ giúp | | |
| Thời gian trung vị T1 (s) | | |
| Thời gian trung vị T2 (s) | | |
| Tổng số lần sai | | |
| Tổng số lần hỏi trợ giúp | | |
| Điểm SUS trung bình | | |

Với 3–5 người, đây là thử nghiệm **định tính có số đo kèm**, không đủ để kết luận thống kê: báo cáo từng người và trung vị, đừng nêu phần trăm hay giá trị p.

## 6. Bảng hỏi SUS (System Usability Scale) bản tiếng Việt

Điền sau mỗi bản (A rồi B), mỗi câu chấm 1–5: **1 = Hoàn toàn không đồng ý, 5 = Hoàn toàn đồng ý.** Với người lớn tuổi, người điều phối đọc to từng câu và ghi lại, không để họ tự điền.

| # | Câu hỏi | A | B |
|---|---------|---|---|
| 1 | Tôi nghĩ tôi sẽ muốn dùng cách này thường xuyên. | | |
| 2 | Tôi thấy cách này phức tạp một cách không cần thiết. | | |
| 3 | Tôi thấy cách này dễ dùng. | | |
| 4 | Tôi nghĩ tôi cần có người kỹ thuật giúp thì mới dùng được cách này. | | |
| 5 | Tôi thấy các phần của cách này được gắn kết với nhau hợp lý. | | |
| 6 | Tôi thấy cách này có quá nhiều chỗ không thống nhất. | | |
| 7 | Tôi nghĩ hầu hết mọi người sẽ học cách dùng này rất nhanh. | | |
| 8 | Tôi thấy cách này rất rườm rà, khó dùng. | | |
| 9 | Tôi cảm thấy rất tự tin khi dùng cách này. | | |
| 10 | Tôi cần học rất nhiều thứ trước khi có thể dùng được cách này. | | |

**Cách tính điểm:** câu lẻ (1, 3, 5, 7, 9): điểm đóng góp = điểm chấm − 1. Câu chẵn (2, 4, 6, 8, 10): điểm đóng góp = 5 − điểm chấm. Tổng 10 điểm đóng góp × 2,5 = **điểm SUS (0–100)**. Điểm ≈ 68 là mức trung bình thường được dùng làm mốc tham khảo; với mẫu nhỏ chỉ dùng để so sánh A với B trên cùng những người.

Câu hỏi mở sau mỗi bản: *"Có chỗ nào bạn thấy bối rối không?"*, *"Bạn có hiểu vì sao link bị chặn không?"*, *"Bạn có thấy yên tâm khi làm theo không?"*

## 7. Quy trình một buổi (khoảng 40 phút)

1. Giới thiệu và **đồng ý tham gia** (mục 8). Hỏi thông tin chung (mã, nhóm tuổi, mức quen dùng máy).
2. Bản đầu (A hoặc B): đọc kịch bản T1 → làm → T2 → làm → SUS → câu hỏi mở.
3. Nghỉ 5 phút; đổi bản (gỡ/nạp lại tiện ích, đổi công cụ của người giám hộ).
4. Bản sau: T1, T2, SUS, câu hỏi mở.
5. Hỏi so sánh: *"Bạn thấy cách nào dễ hơn? Vì sao?"* Cảm ơn, giải thích rằng **link thử là địa chỉ nội bộ**, không có trang lừa đảo nào bị mở.
6. Sau buổi: gỡ tiện ích, chạy `-remove.reg`, xóa bí mật thử khỏi trang người giám hộ ("Xóa khỏi thiết bị này") và xóa tin nhắn thử.

## 8. Lưu ý đạo đức

- **Đồng ý tham gia:** giải thích mục đích, thời lượng, việc ghi chép; người tham gia ký hoặc đồng ý bằng lời (ghi lại) và **có quyền dừng bất kỳ lúc nào** mà không cần lý do. Nói rõ: *"Chúng tôi đo cách dùng, không đo bạn."* Nếu người tham gia bối rối hoặc mệt thì dừng ngay, đừng ép hoàn thành.
- **Không dùng tài khoản thật:** không đăng nhập Zalo/ngân hàng của người tham gia; dùng tài khoản thử hoặc kênh thay thế (mục 2). Không mở thông tin cá nhân của họ.
- **Không dùng link lừa đảo thật:** chỉ dùng link thử tới địa chỉ nội bộ (`192.168.x.x`) hoặc tên miền chắc chắn không tồn tại; không bao giờ cho người tham gia mở trang lừa đảo thật, kể cả khi thử "Cho mở".
- **Quyền riêng tư:** ghi bằng mã (P1…), không ghi tên/số điện thoại cùng với kết quả; không quay hình/ghi âm nếu không có đồng ý riêng bằng văn bản; xóa dữ liệu thô sau khi tổng hợp.
- **Không gây lo sợ:** sau buổi, nói rõ rằng link chỉ là tình huống giả lập; nhắc nguyên tắc thật ("link lạ → Đóng, hỏi người giám hộ"). Không đổ lỗi khi người tham gia làm sai: lỗi là của thiết kế.
- **Người giám hộ thử nghiệm là người đồng ý tham gia** (kể cả khi là người nhà), và cũng được quyền dừng.
- **Hạn chế cần ghi trong báo cáo:** mẫu nhỏ, người tham gia biết mình đang được quan sát, người giám hộ do người điều phối đóng, tình huống giả lập không có áp lực hối thúc thật của kẻ lừa đảo.
