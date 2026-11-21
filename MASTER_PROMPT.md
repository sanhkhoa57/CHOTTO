Bạn là senior security engineer kiêm người hướng dẫn đồ án môn học. Bạn đang làm việc trong repo CHOTTO trên máy Windows của tôi (PowerShell, Python).

## Bối cảnh
CHOTTO là công cụ chấm điểm link lừa đảo trên Zalo (bản Desktop + tiện ích trình duyệt), gồm 3 tầng: Tầng 1 blacklist, Tầng 2 heuristics tiếng Việt, Tầng 3 tuổi tên miền (RDAP/WHOIS). Đây là ĐỒ ÁN MÔN HỌC mảng Cybersecurity, hạn khoảng 1 tuần.

Câu hỏi nghiên cứu: "Các blacklist chỉ chặn được link sau khi có người báo cáo. CHOTTO (chỉ Tầng 2, không blacklist, không tra tuổi) cảnh báo được bao nhiêu % tên miền lừa đảo mới ngay lúc thấy lần đầu, và sớm hơn từng blacklist bao nhiêu giờ?" Tôi gọi đây là "khoảng trống zero-day".

## Việc đầu tiên
1. Đọc CLAUDE.md, README.md, chotto/engine.py, chotto/config.py, tools/eval_accuracy.py để hiểu cấu trúc. Repo của tôi có thể khác bản trên GitHub (có thêm android/, pyproject.toml, uv.lock...). Hãy theo đúng code đang có trên máy.
2. Kiểm tra môi trường: phiên bản Python, có dùng uv không, chạy test hiện có (`python -m unittest discover -s tests` hoặc lệnh trong CLAUDE.md).

## Việc cần làm
### A. Script thu thập (tools/zero_day_gap.py)
- Nếu file đã có trong tools/, đọc kỹ, chạy thử, sửa cho khớp API engine hiện tại. Nếu chưa có thì viết mới với 3 lệnh:
  - `collect`: tải các feed (Phishing.Database NEW-last-hour và ACTIVE, OpenPhish, URLhaus, ChongLuaDao). Ghi vào SQLite thời điểm mỗi tên miền đăng ký xuất hiện lần đầu ở TỪNG nguồn, và chấm điểm bằng Engine (tắt Tầng 1 và Tầng 3) ngay lần đầu thấy. Lần chạy đầu tiên của mỗi nguồn là baseline và bị loại khỏi phân tích. Nguồn nào lỗi mạng thì bỏ qua, không làm hỏng cả lần chạy.
  - `status`: số lần chạy, số ngày, số tên miền mới, tỷ lệ thành công từng nguồn.
  - `report --md --json`: tỷ lệ cảnh báo (điểm ≥ ngưỡng friction trong rules.json), và với từng nguồn: số tên miền chưa được liệt kê, liệt kê muộn hơn, cùng lúc, cùng Q1/trung vị/Q3 số giờ CHOTTO sớm hơn.
- Viết unit test cho script trong tests/ dùng feed giả (file://), không gọi mạng thật.
- Chạy thử thật một lần `collect` và cho tôi xem nguồn nào tải được, nguồn nào lỗi.

### B. Chạy định kỳ trên Windows
- Tạo script PowerShell `tools/schedule_zero_day.ps1` đăng ký Task Scheduler chạy `collect` mỗi 30 phút, dùng đúng đường dẫn Python/uv của máy tôi và thư mục repo hiện tại (đường dẫn có dấu tiếng Việt và khoảng trắng, nhớ đặt trong ngoặc kép). Kèm lệnh gỡ task.
- Ghi log mỗi lần chạy ra file để tôi kiểm tra.
- Tự chạy script để đăng ký task (chỉ cho user hiện tại, không cần quyền Administrator), rồi kiểm tra task đã chạy được ít nhất 1 lần.

### C. Phân tích bổ sung (làm sau khi đã có dữ liệu ≥ 3 ngày)
- Thêm vào `report`: phân bố điểm, top tín hiệu (signal code) xuất hiện ở các tên miền bị bắt; danh sách các tên miền bị BỎ SÓT nhiều nhất theo nhóm (để phân tích vì sao lọt).
- Vẽ 2 biểu đồ (matplotlib, lưu PNG vào docs/): CDF số giờ CHOTTO sớm hơn từng nguồn; cột tỷ lệ bắt theo nhóm (nhắm VN và toàn cầu).

### D. Viết báo cáo
- Tạo `docs/BAO-CAO-ZERO-DAY.md` bằng tiếng Việt, cấu trúc: Đặt vấn đề, Liên quan (blacklist, Google Safe Browsing, ChongLuaDao), Phương pháp, Kết quả (bảng + biểu đồ), Hạn chế, Kết luận. Mục Hạn chế phải nêu trung thực: độ phân giải theo chu kỳ thu thập, mẫu thiên lệch về link đã bị báo cáo, nguồn lỗi, không biết thời điểm tên miền thực sự được dùng để lừa.

## Quy tắc
- KHÔNG sửa chotto/data/rules.json hay logic engine trong thời gian đo, nếu không kết quả sẽ không còn khách quan. Nếu thấy cần cải tiến luật, ghi vào docs/Y-TUONG-CAI-TIEN.md để làm sau.
- Chỉ dùng thư viện chuẩn cho script thu thập; matplotlib chỉ dùng cho phần vẽ biểu đồ.
- Không gửi URL đầy đủ của tôi ra bên ngoài ngoài các feed đã liệt kê.
- Tôi muốn bạn TỰ CHẠY TỪ ĐẦU ĐẾN CUỐI, không dừng lại hỏi. Mỗi bước xong thì chạy test và commit git với message rõ ràng, rồi làm bước tiếp. Nếu bước C/D chưa đủ dữ liệu (dưới 3 ngày) thì vẫn viết sẵn code, khung báo cáo và chạy với dữ liệu hiện có, đánh dấu chỗ cần cập nhật số liệu sau.
- Không xóa file ngoài những file bạn tạo, không push lên GitHub, không cài phần mềm toàn hệ thống. Cuối cùng tóm tắt tất cả việc đã làm và những gì tôi cần làm tiếp.

Bắt đầu với "Việc đầu tiên" và làm liền mạch đến hết.
