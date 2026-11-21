#!/usr/bin/env python3
"""Sinh ``tests/data/guardian_vectors.json``: vector kiểm thử DÙNG CHUNG giữa ``tools/guardian.py`` (Python)
và ``extension/src/guardian/*`` (JavaScript).

Toàn bộ khóa/bí mật trong file này là KHÓA THỬ NGHIỆM cố định, công khai, không dùng cho thật.
Ed25519 là tất định nên chữ ký tái tạo được từng byte.
"""
from __future__ import annotations

import base64
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
CASES: Final[tuple[tuple[str, str], ...]] = (
    ("vietcombank-xacthuc.top", "K7QF3MZD"),
    ("example.com", "AAAAAAAA"),
    ("xn--vietcmbank-ilb.com", "ZZZZ7777"),
    ("momo-hoantien.vip", "K7QF3MZD"),
    ("192.168.1.10", "QWERTYUI"),
    ("a.b.c.example.co.uk", "234567AB"),
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
        "nonce_bytes": [{"hex": h, "base32": base64.b32encode(bytes.fromhex(h)).decode("ascii")}
                        for h in ("0000000000", "ffffffffff", "0102030405", "deadbeef01")],
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
