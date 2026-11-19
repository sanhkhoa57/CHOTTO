# Khoảng trống zero-day – số liệu thu thập

*Tạo lúc 2026-11-19 04:42 UTC. Thu thập 131 lần, từ 2026-11-16 13:41 UTC đến 2026-11-19 04:18 UTC (2.61 ngày).*

> **CẦN CẬP NHẬT SỐ LIỆU:** mới có dưới 3 ngày dữ liệu, các con số dưới đây chưa đủ tin cậy.

## Tỷ lệ cảnh báo ngay lúc thấy lần đầu (chỉ Tầng 2)

Cảnh báo = điểm ≥ 30; HIGH = điểm ≥ 60.

| Nhóm | Số tên miền mới | Cảnh báo | Tỷ lệ | HIGH |
| --- | ---: | ---: | ---: | ---: |
| Tất cả | 3310 | 1330 | 40.2% | 814 |
| Nhắm VN (.vn / thương hiệu VN) | 69 | 69 | 100.0% | 69 |
| Toàn cầu | 3241 | 1261 | 38.9% | 745 |

## So với từng nguồn blacklist

| Nguồn | Tên miền xét | Chưa liệt kê | Liệt kê muộn hơn | Cùng lúc | Loại (baseline) | Số giờ sớm hơn Q1 | Trung vị | Q3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CERT-PL | 3309 | 1349 | 1 | 1959 | 1 | 5.5 | 5.5 | 5.5 |
| OpenPhish | 3310 | 2095 | 20 | 1195 | 0 | 6.2 | 6.5 | 6.5 |
| PhishTank | 3296 | 3079 | 59 | 158 | 14 | 2.5 | 3.5 | 5.5 |

Số giờ sớm hơn chỉ tính trên tên miền CHOTTO cảnh báo được và nguồn liệt kê muộn hơn. "Cùng lúc" gồm cả nguồn đã phát hiện tên miền đầu tiên. "Chưa liệt kê" có thể thành "muộn hơn" ở các lần đo sau (dữ liệu bị cắt phải).

Nguồn bị loại khỏi bảng vì tải được hơn 24 giờ mà không có mục mới nào (nghi ngừng cập nhật): PhishingDB-ACTIVE, PhishingDB-NEW.

## Phân bố điểm

| Điểm | Số tên miền |
| --- | ---: |
| 0-9 | 1089 |
| 10-19 | 810 |
| 20-29 | 81 |
| 30-39 | 332 |
| 40-49 | 52 |
| 50-59 | 132 |
| 60-79 | 435 |
| 80-100 | 379 |

## Dấu hiệu (signal) hay gặp

Ở tên miền bị bắt: `free_hosting` (1120), `entropy` (892), `hyphens` (828), `http` (531), `digits` (372), `tld` (184), `combosquat` (67), `typosquat` (6), `shortener` (2), `homoglyph` (1)

Ở tên miền bị bỏ sót (dấu hiệu có điểm nhưng không đủ ngưỡng): `tld` (691), `entropy` (82), `digits` (63), `http` (62), `hyphens` (55), `idn` (1)

## Tên miền bị bỏ sót (1980)

Theo đuôi: .com (586), .shop (393), .digital (140), .pro (135), .store (104), .top (75), .click (71), .cfd (38), .info (35), .org (28), .net (26), .sbs (23), .xyz (19), .life (18), .online (16)

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
