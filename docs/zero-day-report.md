# Khoảng trống zero-day – số liệu thu thập

*Tạo lúc 2026-11-17 04:57 UTC. Thu thập 36 lần, từ 2026-11-16 13:41 UTC đến 2026-11-17 04:56 UTC (0.64 ngày).*

> **CẦN CẬP NHẬT SỐ LIỆU:** mới có dưới 3 ngày dữ liệu, các con số dưới đây chưa đủ tin cậy.

## Tỷ lệ cảnh báo ngay lúc thấy lần đầu (chỉ Tầng 2)

Cảnh báo = điểm ≥ 30; HIGH = điểm ≥ 60.

| Nhóm | Số tên miền mới | Cảnh báo | Tỷ lệ | HIGH |
| --- | ---: | ---: | ---: | ---: |
| Tất cả | 230 | 170 | 73.9% | 113 |
| Nhắm VN (.vn / thương hiệu VN) | 12 | 12 | 100.0% | 12 |
| Toàn cầu | 218 | 158 | 72.5% | 101 |

## So với từng nguồn blacklist

| Nguồn | Tên miền xét | Chưa liệt kê | Liệt kê muộn hơn | Cùng lúc | Loại (baseline) | Số giờ sớm hơn Q1 | Trung vị | Q3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CERT-PL | 229 | 229 | 0 | 0 | 1 | – | – | – |
| OpenPhish | 230 | 0 | 0 | 230 | 0 | – | – | – |
| PhishingDB-ACTIVE | 230 | 230 | 0 | 0 | 0 | – | – | – |
| PhishingDB-NEW | 230 | 230 | 0 | 0 | 0 | – | – | – |

Số giờ sớm hơn chỉ tính trên tên miền CHOTTO cảnh báo được và nguồn liệt kê muộn hơn. "Cùng lúc" gồm cả nguồn đã phát hiện tên miền đầu tiên. "Chưa liệt kê" có thể thành "muộn hơn" ở các lần đo sau (dữ liệu bị cắt phải).

## Phân bố điểm

| Điểm | Số tên miền |
| --- | ---: |
| 0-9 | 37 |
| 10-19 | 8 |
| 20-29 | 15 |
| 30-39 | 24 |
| 40-49 | 5 |
| 50-59 | 28 |
| 60-79 | 72 |
| 80-100 | 41 |

## Dấu hiệu (signal) hay gặp

Ở tên miền bị bắt: `free_hosting` (165), `hyphens` (105), `entropy` (97), `http` (73), `digits` (63), `combosquat` (11), `tld` (5), `shortener` (2)

Ở tên miền bị bỏ sót (dấu hiệu có điểm nhưng không đủ ngưỡng): `http` (15), `tld` (4), `entropy` (2), `hyphens` (2)

## Tên miền bị bỏ sót (60)

Theo đuôi: .com (32), .cc (3), .mx (2), .top (2), .de (2), .gr (2), .it (1), .info (1), .xyz (1), .lu (1), .co (1), .uk (1), .site (1), .dev (1), .pl (1)

Theo nền tảng hosting: –

### Mẫu bị bỏ sót – toàn cầu

| Tên miền | Điểm | Dấu hiệu |
| --- | ---: | --- |
| addliav.com | 0 | – |
| addliqa.com | 27 | http |
| addliqd.com | 0 | – |
| addliqf.com | 0 | – |
| addliqg.cc | 0 | – |
| addliqg.com | 0 | – |
| addliqi.com | 0 | – |
| addliqk.com | 0 | – |
| addliql.com | 0 | – |
| addliqo.com | 0 | – |
| addliqs.com | 27 | http |
| addliqw.com | 0 | – |
| addliqz.com | 0 | – |
| agentforce.cc | 0 | – |
| alosys.it | 0 | – |
| ambitopv.com | 27 | http |
| ananeosi-support.com | 27 | http |
| atron-solutions.com | 0 | – |
| cabletu-mrsm.com.mx | 0 | – |
| chasincocktails.com | 13 | entropy |
| compass-nav.info | 0 | – |
| conatem.com | 27 | http |
| cursos-zensara.com | 0 | – |
| dapp-coin.top | 18 | tld |
| eventzones.de | 27 | http |
| flowcode.com | 27 | http |
| folve.xyz | 18 | tld |
| g5.lu | 0 | – |
| gamez-mlbb.com | 27 | http |
| hh-homebase.de | 27 | http |
