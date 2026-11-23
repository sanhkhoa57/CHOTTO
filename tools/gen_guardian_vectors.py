#!/usr/bin/env python3
"""Sinh ``tests/data/guardian_vectors.json``: vector kiểm thử DÙNG CHUNG giữa ``tools/guardian.py`` (Python)
và ``platforms/extension/src/guardian/*`` (JavaScript).

Toàn bộ khóa/bí mật trong file này là KHÓA THỬ NGHIỆM cố định, công khai, không dùng cho thật.
Ed25519 là tất định nên chữ ký tái tạo được từng byte.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import guardian  # noqa: E402

OUT: Final[Path] = ROOT / "tests" / "data" / "guardian_vectors.json"
TEST_SECRET: Final[bytes] = bytes(range(32))
TEST_SEED: Final[bytes] = bytes(range(100, 132))
SHARE_PAGE: Final[str] = "https://example.github.io/CHOTTO/guardian/"
CASES: Final[tuple[tuple[str, str], ...]] = (
    ("vietcombank-xacthuc.top", "K7QF3MZDX9HP"),
    ("example.com", "AAAAAAAAAAAA"),
    ("xn--vietcmbank-ilb.com", "ZZZZ7777ZZZZ"),
    ("momo-hoantien.vip", "K7QF3MZDX9HP"),
    ("192.168.1.10", "QWERTYUPASDF"),
    ("a.b.c.example.co.uk", "23456789ABCD"),
)
# Dòng byte ngẫu nhiên → nonce (byte >= 248 bị bỏ; lấy đủ 12 ký tự). Có cả trường hợp bỏ byte lệch và không đủ byte.
NONCE_STREAMS: Final[tuple[str, ...]] = (
    "000102030405060708090a0b",
    "f7f6f5f4f3f2f1f0efeeedec",
    "f8f9fafbfcfdfeff000102030405060708090a0b0c0d",
    "deadbeef0123456789abcdef0011223344556677",
    "f8f8f8f8",
)
# Tên người giám hộ: đầu vào → kết quả sau khi lọc (``None`` = bỏ). Có ký tự điều khiển, vô hình, đảo chiều, quá dài.
NAME_CASES: Final[tuple[str, ...]] = (
    "Mai", "  Bà   Lan  ", "Con‮evil​", "Hà\x00\x07 Nội", "<b>Mai</b>", "\n\t ", "",
    "Nguyễn Thị Thanh Tâm Nguyễn Thị Thanh Tâm", "\U0001F600" * 40, "Ông Ba",
)
# Địa chỉ trang người giám hộ: đầu vào → kết quả (``None`` = bỏ, dùng mặc định).
PAGE_URL_CASES: Final[tuple[str, ...]] = (
    "https://example.github.io/CHOTTO/guardian/", "https://example.com/g/?x=1#frag", "http://localhost:8080/guardian/",
    "http://example.com/guardian/", "https://user:pw@example.com/", "javascript:alert(1)", "https://example.com", "",
)


def build() -> dict[str, Any]:
    """Dựng nội dung vector."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    codes = [{"domain": d, "nonce": n, "message": guardian.challenge_message(d, n),
              "code": guardian.compute_code(TEST_SECRET, d, n)} for d, n in CASES]
    private = Ed25519PrivateKey.from_private_bytes(TEST_SEED)
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    payload = guardian.build_policy_payload(
        {"allow_domains": ["Vietcombank.com.vn."], "require_levels": ["HIGH"], "challenge_ttl_sec": 300}, 7)
    payload = json.dumps({**json.loads(payload), "issued_at": 1_700_000_000}, sort_keys=True, separators=(",", ":"))
    return {
        "about": "Sinh bởi tools/gen_guardian_vectors.py. Khóa thử nghiệm công khai, KHÔNG dùng cho thật.",
        "hmac_secret": guardian.b64u(TEST_SECRET),
        "codes": codes,
        "nonce_alphabet": guardian.NONCE_ALPHABET,
        "nonce_streams": [{"hex": h, "nonce": guardian.nonce_from_bytes(bytes.fromhex(h))} for h in NONCE_STREAMS],
        "names": [{"input": n, "expected": guardian.sanitize_name(n)} for n in NAME_CASES],
        "page_urls": [{"input": u, "expected": guardian.sanitize_page_url(u)} for u in PAGE_URL_CASES],
        "share_links": [{"page": SHARE_PAGE, "domain": d, "nonce": n, "link": guardian.build_share_link(SHARE_PAGE, d, n)}
                        for d, n in CASES],
        "policy": {
            "public_key": guardian.b64u(public),
            "payload": payload,
            "signature": guardian.sign_payload(guardian.b64u(TEST_SEED), payload),
        },
    }


def main() -> int:
    """Ghi file vector."""
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(f"Đã ghi {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
