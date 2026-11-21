# Ý tưởng cải tiến (làm SAU khi đo xong)

Trong thời gian đo khoảng trống zero-day **không được sửa** `chotto/data/rules.json` hay logic engine, nếu không
kết quả không còn khách quan. Mọi ý tưởng cải tiến luật ghi vào đây.

Ý tưởng đã có sẵn từ phần công cụ đo (chưa kiểm chứng bằng số liệu):

1. **Feed chỉ có tên miền làm mất tín hiệu đường dẫn.** Nếu `report` cho thấy tên miền bị bỏ sót chủ yếu đến từ
   Phishing.Database ACTIVE, thử lấy thêm bản `phishing-links-ACTIVE.txt` (có URL đầy đủ) để đo lại.
2. **Nền tảng hosting miễn phí.** Xem mục "Theo nền tảng hosting" trong `docs/zero-day-report.md`: nếu vài nền tảng
   chiếm phần lớn tên miền lọt, cân nhắc tăng trọng số `free_hosting` kết hợp với từ khóa dụ dỗ.
3. **Đuôi tên miền.** Xem "Theo đuôi" trong cùng báo cáo để biết đuôi nào hay lọt mà chưa nằm trong `high_risk_tlds`.
4. **Dấu hiệu hay gặp ở tên miền bị bỏ sót.** Mục "Dấu hiệu hay gặp" cho biết dấu hiệu nào có xuất hiện nhưng điểm
   quá thấp để vượt ngưỡng 30; dùng `tools/calibrate_weights.py` để thử trọng số mới trên tập giữ riêng.
5. **Nguồn dữ liệu Việt Nam.** Tìm đường dẫn thay thế cho ChongLuaDao (API hiện không phân giải) và URLhaus (bản tải
   công khai bị gỡ, cần khóa API của abuse.ch) để có nguồn so sánh đúng bối cảnh. Đã thử (16/11/2026): bản sao `vn-badsite-filter` (curbengh, lấy từ ChongLuaDao) vẫn tải được nhưng
   dòng `Updated` là 2025-04-11, tức đã ngừng cập nhật, nên KHÔNG dùng được để đo thời điểm liệt kê.
6. **Thu thập độc lập với Task Scheduler.** Nếu máy hay ngủ làm hỏng chu kỳ 30 phút, chạy `collect` trên một máy chủ
   luôn bật (ví dụ GitHub Actions theo lịch) để có độ phân giải ổn định hơn.

Mọi thay đổi luật sau này phải đo lại bằng `tools/eval_accuracy.py` (báo nhầm) và chạy lại toàn bộ test.
