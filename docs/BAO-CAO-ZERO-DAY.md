# Khoảng trống zero-day của link lừa đảo: CHOTTO (Tầng 2) đi trước blacklist bao lâu?

> **Trạng thái: bản chốt (19/11/2026 14:00 UTC).** Thu thập 150 lần trong đúng 3,0 ngày (16/11 13:41 → 19/11 13:48 UTC),
> 5.360 tên miền mới. Số liệu gốc: `docs/zero-day-report.md` và `docs/zero-day-report.json`. Thu thập vẫn đang chạy;
> muốn cập nhật số liệu dài hơn thì xem mục cuối.

## 1. Đặt vấn đề

Blacklist chỉ chặn được một link **sau khi** có người báo cáo hoặc hệ thống của nhà cung cấp quét ra nó. Lừa đảo
trên Zalo thì ngược lại: tên miền thường được đăng ký, dùng trong vài giờ đến vài ngày rồi bỏ. Khoảng thời gian từ lúc
link bắt đầu lan truyền đến lúc nó lọt vào blacklist là **khoảng trống zero-day**, và trong khoảng này blacklist
không giúp được người nhận link.

CHOTTO có ba tầng: Tầng 1 là blacklist, Tầng 2 là heuristic tiếng Việt chạy cục bộ (hình dạng tên miền, từ khóa
dụ dỗ, mạo danh thương hiệu, link bọc...), Tầng 3 tra tuổi tên miền. Tầng 2 không cần ai báo cáo trước nên là phần
duy nhất của CHOTTO có thể lấp khoảng trống này.

**Câu hỏi nghiên cứu.** *CHOTTO, chỉ dùng Tầng 2 (không blacklist, không tra tuổi), cảnh báo được bao nhiêu % tên miền
lừa đảo mới ngay lúc thấy lần đầu, và sớm hơn từng blacklist bao nhiêu giờ?*

## 2. Các công trình và nguồn liên quan

- **Blacklist cộng đồng và thương mại.** Phishing.Database (mitchellkrogza, giấy phép MIT), OpenPhish (feed công
  khai), PhishTank, URLhaus (abuse.ch). Chúng khác nhau về cách thu thập (báo cáo của người dùng, crawler, kiểm tra
  còn sống) nên độ trễ khác nhau.
- **Google Safe Browsing.** Dịch vụ lớn nhất, tích hợp trong trình duyệt. Nó cũng là danh sách, nên cùng bản chất:
  chỉ có hiệu lực sau khi URL được phát hiện và phân loại. Báo cáo này **không đo** Safe Browsing vì không có feed
  công khai đủ để so sánh theo thời gian mà không gửi URL cho dịch vụ bên ngoài (xem mục Hạn chế).
- **ChongLuaDao.** Dự án cộng đồng Việt Nam, nguồn blacklist chính của CHOTTO (`rules.json`, `blacklist_sources`).
  Đây là nguồn có giá trị nhất để so sánh vì nhắm đúng bối cảnh Việt Nam, nhưng API của họ **không truy cập được**
  trong đợt đo này (xem mục 4).
- **Độ chính xác tĩnh của CHOTTO.** `docs/BAO-CAO-DO-CHINH-XAC.md` đo Tầng 2 trên một danh sách lừa đảo cố định (không
  có yếu tố thời gian): bắt được 24,4% link nhắm VN và 40,6% link toàn cầu ở v1.3. Báo cáo này đặt thêm trục thời
  gian, nên nó cho biết Tầng 2 đi trước blacklist bao lâu chứ không chỉ bắt được bao nhiêu phần trăm.

## 3. Phương pháp

Công cụ: `tools/zero_day_gap.py` (chỉ dùng thư viện chuẩn). Dữ liệu nằm trong SQLite `.zero-day/zero_day.sqlite3`.

1. **Thu thập.** Cứ 30 phút (`tools/schedule_zero_day.ps1`, Task Scheduler) lệnh `collect` tải các feed:
   OpenPhish, PhishTank (CSV, cập nhật hàng giờ) và CERT Polska (`hole.cert.pl`, danh sách tên miền độc hại), kèm URLhaus
   và ChongLuaDao (hiện lỗi, vẫn thử lại). Từ 17/11/2026 bỏ Phishing.Database vì kho ngừng cập nhật (xem 4.1).
2. **Ghi nhận lần đầu.** Với mỗi *tên miền đăng ký được* (theo Public Suffix List, gồm cả phần PRIVATE nên
   `x.weeblysite.com` được tính riêng), lưu thời điểm nó xuất hiện lần đầu ở **từng nguồn**.
3. **Baseline.** Lần chạy thành công đầu tiên của mỗi nguồn là baseline. Tên miền chỉ thấy ở baseline bị loại vì
   không biết chúng đã tồn tại từ bao giờ. Tên miền nằm trong baseline của nguồn nào thì nguồn đó bị loại khỏi thống kê
   của riêng tên miền đó.
4. **Chấm điểm ngay lúc thấy.** Tên miền mới (chưa nguồn nào từng có) được chấm bằng `Engine` với Tầng 1 và Tầng 3
   tắt, nên không có mạng và không có blacklist. Feed chỉ có tên miền thì chấm dưới dạng `https://tên-miền/`; feed có
   URL đầy đủ thì chấm URL đó. Mốc T0 là thời điểm lần chạy `collect` phát hiện ra tên miền.
5. **Chỉ số.**
   - *Tỷ lệ cảnh báo*: điểm ≥ ngưỡng friction trong `rules.json` (30), tách nhóm nhắm VN (đuôi `.vn` hoặc chứa thương
     hiệu VN, cùng tiêu chí với `eval_accuracy.py`) và toàn cầu.
   - *Với từng nguồn*: số tên miền chưa được liệt kê, liệt kê muộn hơn, cùng lúc; và Q1/trung vị/Q3 của (giờ nguồn
     liệt kê − T0), chỉ tính tên miền CHOTTO cảnh báo được.
6. **Giữ khách quan.** `chotto/data/rules.json` và logic engine **không được sửa** trong thời gian đo. Ý tưởng cải
   tiến luật ghi ở `docs/Y-TUONG-CAI-TIEN.md`.

Kiểm thử: `tests/test_zero_day_gap.py` (17 bài, feed giả `file://`, không gọi mạng).

## 4. Kết quả

### 4.1. Tình trạng thu thập

Lần thu thập đầu tiên (16/11/2026 13:41 UTC), thực tế:

| Nguồn | Kết quả | Mục baseline |
| --- | --- | ---: |
| Phishing.Database ACTIVE (domains) | tải được | 290.421 |
| OpenPhish | tải được | 261 |
| Phishing.Database NEW-last-hour (links) | tải được, nhưng file **rỗng** lúc đó | 0 |
| URLhaus (`text_recent`) | **lỗi HTTP 410 Gone** (bản tải công khai không còn phục vụ) | – |
| ChongLuaDao (`api.chongluadao.vn/v1/blacklist`) | **lỗi DNS**, tên miền API không phân giải | – |

Đã thử bản sao cộng đồng của ChongLuaDao (`vn-badsite-filter`): tải được nhưng ngừng cập nhật từ 11/04/2025 nên không dùng. **Phát hiện ngày 17/11/2026:** kho Phishing.Database có commit cuối vào 02/10/2026; feed NEW-last-hour luôn rỗng và
ACTIVE giữ nguyên 290.421 mục suốt 15 giờ đo, nên hai feed này không cho dữ liệu thời gian. Sau 35 lần chạy, chỉ
OpenPhish thêm mục mới (240 tên miền), vì vậy 230 tên miền đã chấm trong ngày đầu đều do OpenPhish phát hiện và **chưa
so sánh được với nguồn thứ hai**. Đã thêm PhishTank và CERT-PL (baseline CERT-PL: 103.064 mục); PhishTank trả
HTTP 429 (giới hạn tần suất tải) ở lần thử đầu, cần theo dõi. Các tên miền đã chấm trước khi một nguồn mới vào đo có thể nằm
trong baseline của nguồn đó và bị loại riêng khỏi thống kê của nguồn đó (cắt trái). Hai nguồn lỗi vẫn nằm trong cấu hình để mỗi lần chạy thử lại; nếu chúng sống lại, lần thành công đầu tiên sẽ là
baseline.

Tỷ lệ tải thành công sau 3 ngày (`python tools/zero_day_gap.py status`):

| Nguồn | Thành công | Ghi chú |
| --- | ---: | --- |
| OpenPhish | 150/150 (100%) | |
| CERT-PL | 114/115 (99%) | một lần hết thời gian chờ SSL |
| PhishTank | 30/81 (37%) | HTTP 429 (giới hạn tần suất); **lần thành công cuối 19/11 08:18 UTC** |
| Phishing.Database (NEW, ACTIVE) | 35/35 | đã bỏ khỏi danh sách từ 17/11, nguồn không đổi, bị loại khỏi bảng so sánh |
| URLhaus | 0/150 | HTTP 410 |
| ChongLuaDao | 0/150 | lỗi DNS |

### 4.2. Tỷ lệ cảnh báo ngay lúc thấy lần đầu

| Nhóm | Số tên miền mới | Cảnh báo | Tỷ lệ | Mức HIGH |
| --- | ---: | ---: | ---: | ---: |
| Tất cả | 5.360 | 1.565 | 29,2% | 969 |
| Nhắm VN | 80 | 80 | 100% | 80 |
| Toàn cầu | 5.280 | 1.485 | 28,1% | 889 |

Cách đọc đúng các con số này:

- **Con số chung 29,2% là kết quả của cơ cấu mẫu, không phải một năng lực duy nhất.** Tỷ lệ bắt phụ thuộc rất mạnh vào
  nguồn phát hiện tên miền:

  | Nguồn phát hiện đầu tiên | Số tên miền | Được cảnh báo | Tỷ lệ |
  | --- | ---: | ---: | ---: |
  | OpenPhish (URL đầy đủ) | 1.429 | 1.237 | 86,6% |
  | PhishTank (URL đầy đủ) | 158 | 38 | 24,1% |
  | CERT-PL (chỉ có tên miền) | 3.773 | 290 | 7,7% |
  | *Hai nguồn có URL đầy đủ gộp lại* | *1.587* | *1.275* | *80,3%* |

  CERT-PL chiếm 70% mẫu và kéo con số chung xuống. Tỷ lệ chung vì thế biến động theo thời gian (40,2% ở 2,6 ngày,
  29,2% ở 3,0 ngày) chỉ do CERT-PL đưa thêm nhiều tên miền một lúc. **Không nên trích con số chung làm "tỷ lệ bắt zero-day"**.
  Cách báo cáo trung thực: *khoảng 80% với link lừa đảo có URL đầy đủ như OpenPhish/PhishTank và khoảng 8% với tên miền
  trần trong danh sách CERT-PL*, kèm các hạn chế ở mục 5.
- **Nhóm "nhắm VN" 100% là vì cách xác định nhóm**: tên miền chứa từ khóa thương hiệu VN thì chính từ khóa đó cũng làm
  Tầng 2 chấm điểm cao (mạo danh thương hiệu). Với n = 80, đây là cận trên, không phải tỷ lệ bắt thật với link nhắm VN.
- Con số 28-29% toàn cầu thấp hơn 40,6% của `BAO-CAO-DO-CHINH-XAC.md` (danh sách tĩnh của Phishing.Database) vì hai
  phép đo khác nguồn: danh sách tĩnh chứa nhiều URL đầy đủ, còn mẫu này có 70% là tên miền trần từ CERT-PL.

![Tỷ lệ bắt theo nhóm](zero-day-rate-by-group.png)

### 4.3. CHOTTO đi trước từng nguồn bao nhiêu giờ

"Xét" là số tên miền không nằm trong baseline của nguồn đó.

| Nguồn | Xét | Chưa liệt kê | Liệt kê muộn hơn | Cùng lúc | Mẫu tính độ trễ | Sớm hơn Q1 / trung vị / Q3 (giờ) |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| PhishTank | 5.346 | 5.125 | 61 | 160 | 34 | 2,5 / 3,5 / 5,5 |
| OpenPhish | 5.360 | 3.909 | 22 | 1.429 | 5 | 6,5 / 6,5 / 6,5 |
| CERT-PL | 5.359 | 1.585 | 1 | 3.773 | 1 | 5,5 (một mẫu) |

"Mẫu tính độ trễ" là tên miền CHOTTO cảnh báo được **và** nguồn liệt kê muộn hơn; chỉ các mẫu này vào cột cuối.

- **Chỉ PhishTank có đủ mẫu để nói điều gì đó:** với 34 tên miền CHOTTO cảnh báo được, PhishTank liệt kê muộn hơn
  trung vị **3,5 giờ** (Q1 2,5, Q3 5,5). Với OpenPhish (5 mẫu, cùng cho 6,5 giờ) và CERT-PL (1 mẫu) chưa đủ để kết luận.
- **Phần lớn tên miền chưa được nguồn nào liệt kê lại** (OpenPhish 73%, PhishTank 96%, CERT-PL 30%). Đó là dữ liệu bị
  cắt phải: khoảng trống thật của các tên miền này lớn hơn thời gian đo, nên con số 3,5 giờ là **cận dưới** và chỉ mô tả
  những tên miền cuối cùng cũng được liệt kê.
- Cột "cùng lúc" gồm cả các tên miền do chính nguồn đó phát hiện đầu tiên, nên không phản ánh tốc độ của nó.
- **PhishTank chỉ tải thành công 37% số lần và lần cuối là 08:18 UTC ngày 19/11**: các tên miền xuất hiện sau mốc đó
  không thể được tính là "đã liệt kê" ở PhishTank, nên con số "chưa liệt kê" của nó (96%) bị thổi phồng.

![CDF số giờ CHOTTO sớm hơn](zero-day-cdf.png)

### 4.4. Vì sao một số tên miền lọt

3.795 tên miền bị bỏ sót (điểm < 30), tức 70,8% mẫu.

- **Phân bố điểm lưỡng cực:** 3.696 tên miền (69%) có điểm dưới 20 và 969 tên miền (18%) từ 60 trở lên; chỉ 99 tên
  miền ở khoảng 20-29. Tầng 2 hoặc thấy rất rõ hoặc gần như không thấy gì, rất ít tên miền nằm sát ngưỡng 30. Vì vậy
  hạ ngưỡng một chút không cứu được phần lớn tên miền lọt.
- **Dấu hiệu giúp bắt được:** `free_hosting` (1.332), `entropy` (1.042), `hyphens` (981), `http` (638), `digits` (425).
  Chỉ 77 tên miền bắt được nhờ `combosquat` và 6 nhờ `typosquat`: cơ chế mạo danh thương hiệu hiếm khi kích hoạt trong mẫu này.
- **Vì sao lọt:** 834 trong 3.795 tên miền bị bỏ sót có dấu hiệu `tld` (đuôi rẻ tiền) nhưng điểm không đủ ngưỡng; phần
  lớn số còn lại không có dấu hiệu nào hoặc chỉ có dấu hiệu nhẹ (`entropy` 106, `http` 74, `digits` 71, `hyphens` 59),
  tức là tên miền trông như một tên miền thương mại bình thường. Đuôi hay lọt: `.com` (1.495), `.store` (656),
  `.shop` (453), `.digital` (167), `.pro` (142), `.space` (136).
- **Tập trung theo chiến dịch:** nhiều tên miền lọt là biến thể của cùng một chiến dịch (ví dụ các họ `truly*`, `choic*`,
  `addli*`, `brigh*`, `clear*`, `insta*`), nên số đếm bị một vài chiến dịch lớn chi phối.
- **Không có tên miền nào lọt nằm trên nền tảng hosting miễn phí**: các tên miền này được tính theo hậu tố PRIVATE của PSL
  và đều được cảnh báo.

Danh sách mẫu bị bỏ sót nằm trong `docs/zero-day-report.md`. Ý tưởng cải tiến (làm sau khi đo xong) nằm ở
`docs/Y-TUONG-CAI-TIEN.md`.

## 5. Hạn chế

1. **Độ phân giải theo chu kỳ thu thập.** Mọi thời điểm là thời điểm của lần chạy `collect` (30 phút). "Cùng lúc"
   nghĩa là cùng một lần chạy, không phải cùng một giây. Chênh lệch dưới 30 phút không đo được. Máy tắt hoặc ngủ thì
   chu kỳ bị kéo dài và mốc T0 bị trễ.
2. **Mẫu thiên lệch về link đã bị báo cáo.** Chỉ những tên miền cuối cùng lọt vào một feed mới có mặt trong dữ liệu.
   Link lừa đảo không bao giờ được báo cáo thì vắng mặt, nên tỷ lệ bắt có thể không đại diện cho toàn bộ lừa đảo trên
   Zalo. Ngoài ra, tên miền lừa đảo nhắm riêng người Việt qua Zalo có thể ít được các feed quốc tế thu thập.
3. **Không biết thời điểm tên miền thực sự được dùng để lừa.** T0 là lúc nghiên cứu thấy tên miền ở một feed, không
   phải lúc nạn nhân nhận link. Tên miền có thể đã lưu hành từ trước, nên khoảng "CHOTTO sớm hơn" tính được là **cận
   dưới** của khoảng trống thật, còn tỷ lệ "chưa liệt kê" bị cắt phải (nguồn có thể liệt kê sau khi đo xong).
4. **Nguồn lỗi.** URLhaus (HTTP 410) và ChongLuaDao (DNS) không tải được, nên báo cáo thiếu đúng nguồn có ý nghĩa
   nhất với Việt Nam. Kết luận chỉ áp dụng cho các nguồn thực sự đo được.
5. **Không đo Google Safe Browsing.** Tra từng URL qua dịch vụ ngoài vi phạm nguyên tắc không gửi URL ra ngoài các feed
   đã liệt kê, và API cần khóa.
6. **Ảnh hưởng của feed chỉ có tên miền.** CERT-PL (và feed Phishing.Database ACTIVE trước đó) chỉ có tên miền, nên điểm của chúng được tính khi mất
   đường dẫn và tham số (nhiều tín hiệu của Tầng 2 nằm ở đó), có thể làm tỷ lệ bắt thấp hơn thực tế.
7. **Nhóm "nhắm VN" xác định bằng quy tắc** (đuôi `.vn` hoặc từ khóa thương hiệu), không phải nhãn thật; tên miền
   chứa từ khóa thương hiệu có thể là trang hợp pháp bị nhầm. Cỡ mẫu nhóm này có thể rất nhỏ.
8. **Tên miền đăng ký theo PSL** coi từng subdomain trên nền tảng hosting (PRIVATE) là một tên miền riêng, nên một
   chiến dịch lớn trên cùng nền tảng có thể làm lệch số đếm.
9. **Cơ cấu mẫu phụ thuộc nguồn.** Nguồn chiếm đa số tên miền (CERT-PL, 70%) quyết định con số chung. Mỗi nguồn có định
   nghĩa "độc hại" và dạng dữ liệu (tên miền trần hay URL đầy đủ) khác nhau, nên các con số theo nguồn đáng tin hơn con số chung.
10. **PhishTank bị giới hạn tần suất** (tải thành công 37%, lần cuối 19/11 08:18 UTC), nên thống kê của nó thiên về
    "chưa liệt kê" sau mốc đó.
11. **Thời gian đo ngắn (3 ngày) và mẫu độ trễ nhỏ** (34/5/1 mẫu). Quartile của OpenPhish và CERT-PL không có ý nghĩa
    thống kê.

## 6. Kết luận

Dựa trên 3,0 ngày dữ liệu (150 lần thu thập, 5.360 tên miền mới, ba nguồn đo được):

1. **Tỷ lệ bắt zero-day phụ thuộc vào dạng dữ liệu.** CHOTTO chỉ với Tầng 2 cảnh báo ngay lần đầu thấy khoảng **80%** link
   lừa đảo có URL đầy đủ (OpenPhish + PhishTank: 1.275/1.587), nhưng chỉ khoảng **8%** tên miền trần trong danh sách
   CERT-PL (290/3.773). Con số gộp 29,2% chỉ phản ánh cơ cấu mẫu và không nên dùng làm tỷ lệ bắt chung. Số 100% của
   nhóm nhắm VN (80/80) chưa đáng tin vì nhóm được xác định bằng đúng tín hiệu thương hiệu.
2. **Khoảng trống zero-day.** Với những tên miền Tầng 2 bắt được mà blacklist liệt kê sau, PhishTank liệt kê muộn hơn
   trung vị **3,5 giờ** (Q1 2,5, Q3 5,5; 34 mẫu). Với OpenPhish và CERT-PL số mẫu quá ít. Phần lớn tên miền (73% với
   OpenPhish, 96% với PhishTank) chưa được liệt kê trong thời gian đo, nên khoảng trống thật có thể lớn hơn 3,5 giờ; đây là cận dưới.
3. **Phần lọt.** 70,8% tên miền bị bỏ sót, chủ yếu là tên miền đuôi rẻ tiền không có dấu hiệu nào khác hoặc trông như tên miền
   thương mại bình thường. Điểm số lưỡng cực (69% dưới 20 điểm, chỉ 99 tên miền ở 20-29), nên chỉnh ngưỡng không giải quyết
   được. Đó là giới hạn của heuristic chỉ dựa vào hình dạng tên miền; Tầng 3 (tuổi tên miền) và blacklist là lớp bổ sung cho nhóm này.
4. Các hạn chế ở mục 5 nghĩa là các con số là **cận dưới/giá trị tham khảo** và chỉ áp dụng cho các nguồn đo được.

---

## Cách cập nhật số liệu

```
python tools/zero_day_gap.py status
python tools/zero_day_gap.py report --md docs/zero-day-report.md --json docs/zero-day-report.json
python tools/zero_day_gap.py plot --out docs
```

rồi cập nhật lại các con số ở mục 4 và 6 từ `docs/zero-day-report.md` (bản chốt này dùng số liệu đến 19/11/2026 13:48 UTC).
