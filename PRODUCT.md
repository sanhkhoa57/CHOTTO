# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Học sinh, sinh viên dùng Zalo trên Windows/macOS (và Android bản beta). Họ hay nhận link lạ qua tin nhắn nhóm/bạn bè (việc làm thêm, trúng thưởng, giả danh ngân hàng, giao hàng) và không có thời gian đọc lý do dài: cần nhìn một giây là biết nguy hiểm hay không. (Người dùng lớn tuổi cũng là đối tượng phụ, theo yêu cầu của thầy hướng dẫn: "đọc và nhìn liền thấy luôn".)

## Product Purpose
Trạm kiểm soát link Zalo: là trình mở link mặc định, kiểm tra mọi link bấm trong Zalo trước khi mở và chặn link đáng ngờ bằng màn hình cảnh báo có độ trễ cố ý. Thành công = người dùng không bị dẫn tới trang lừa đảo mà không mất thời gian với link an toàn (link an toàn mở ngay).

## Positioning
Chặn ngay tại lúc bấm link trong Zalo (không cần chủ động kiểm tra), chạy offline và riêng tư (chỉ lưu tên miền trên máy), cố ý làm chậm nút "vẫn mở" để người dùng kịp suy nghĩ.

## Operating Context
Desktop (Windows/macOS, pywebview + HTML), tiện ích Chrome/Edge, Android (Kotlin/Compose, beta). Ba tầng kiểm tra: danh sách đen, phân tích URL, tra tuổi tên miền (tùy chọn, cần mạng). Giao diện song ngữ EN/VI (`ui_language`, mặc định EN).

## Capabilities and Constraints
- Màn hình cảnh báo là fail-safe: lỗi giao diện thì lùi về Tk; đóng cửa sổ = "không mở"; thời gian khóa do tiến trình giao diện tự kiểm lại.
- Lý do kỹ thuật phải thu gọn; điểm rủi ro 0-100 và mức độ phải thấy ngay.
- Mã dấu hiệu mới phải có bản dịch EN/VI (có test kiểm tra).
- Chưa ký số (Windows SmartScreen, macOS chưa công chứng).

## Brand Commitments
Tên Chotto, nhà phát triển AECCUS. Logo chính `assets/logo.png`. Chưa ràng buộc phong cách thị giác (người dùng đã đổi hướng nhiều lần).

## Evidence on Hand
Mã nguồn, bộ vector kiểm thử (`tests/data`), ảnh chụp giao diện trong `docs/ui`. Không có số liệu người dùng thật hay lời chứng thực: không được bịa.

## Product Principles
1. Nhìn một giây là hiểu: mức nguy hiểm và điểm số phải lớn hơn mọi thứ khác.
2. Ma sát có chủ đích: chậm đúng chỗ (link nguy hiểm), nhanh đúng chỗ (link an toàn).
3. Riêng tư theo mặc định: không gửi link đi đâu.
4. Lý do có sẵn nhưng không bắt đọc.

## Accessibility & Inclusion
Độ tương phản đạt WCAG AA; chữ lớn; tôn trọng reduced-motion; tiếng Việt có dấu đầy đủ.
