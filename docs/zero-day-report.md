# Khoảng trống zero-day – số liệu thu thập

*Tạo lúc 2026-11-19 14:02 UTC. Thu thập 150 lần, từ 2026-11-16 13:41 UTC đến 2026-11-19 13:48 UTC (3.0 ngày).*

## Tỷ lệ cảnh báo ngay lúc thấy lần đầu (chỉ Tầng 2)

Cảnh báo = điểm ≥ 30; HIGH = điểm ≥ 60.

| Nhóm | Số tên miền mới | Cảnh báo | Tỷ lệ | HIGH |
| --- | ---: | ---: | ---: | ---: |
| Tất cả | 5360 | 1565 | 29.2% | 969 |
| Nhắm VN (.vn / thương hiệu VN) | 80 | 80 | 100.0% | 80 |
| Toàn cầu | 5280 | 1485 | 28.1% | 889 |

## So với từng nguồn blacklist

| Nguồn | Tên miền xét | Chưa liệt kê | Liệt kê muộn hơn | Cùng lúc | Loại (baseline) | Số giờ sớm hơn Q1 | Trung vị | Q3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CERT-PL | 5359 | 1585 | 1 | 3773 | 1 | 5.5 | 5.5 | 5.5 |
| OpenPhish | 5360 | 3909 | 22 | 1429 | 0 | 6.5 | 6.5 | 6.5 |
| PhishTank | 5346 | 5125 | 61 | 160 | 14 | 2.5 | 3.5 | 5.5 |

Số giờ sớm hơn chỉ tính trên tên miền CHOTTO cảnh báo được và nguồn liệt kê muộn hơn. "Cùng lúc" gồm cả nguồn đã phát hiện tên miền đầu tiên. "Chưa liệt kê" có thể thành "muộn hơn" ở các lần đo sau (dữ liệu bị cắt phải).

Nguồn bị loại khỏi bảng vì tải được hơn 24 giờ mà không có mục mới nào (nghi ngừng cập nhật): PhishingDB-ACTIVE, PhishingDB-NEW.

## Phân bố điểm

| Điểm | Số tên miền |
| --- | ---: |
| 0-9 | 2721 |
| 10-19 | 975 |
| 20-29 | 99 |
| 30-39 | 370 |
| 40-49 | 64 |
| 50-59 | 162 |
| 60-79 | 528 |
| 80-100 | 441 |

## Dấu hiệu (signal) hay gặp

Ở tên miền bị bắt: `free_hosting` (1332), `entropy` (1042), `hyphens` (981), `http` (638), `digits` (425), `tld` (205), `combosquat` (77), `typosquat` (6), `shortener` (2), `homoglyph` (1)

Ở tên miền bị bỏ sót (dấu hiệu có điểm nhưng không đủ ngưỡng): `tld` (834), `entropy` (106), `http` (74), `digits` (71), `hyphens` (59), `idn` (1)

## Tên miền bị bỏ sót (3795)

Theo đuôi: .com (1495), .store (656), .shop (453), .digital (167), .pro (142), .space (136), .top (103), .click (74), .cfd (44), .info (41), .cyou (35), .net (31), .org (29), .sbs (27), .live (25)

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
