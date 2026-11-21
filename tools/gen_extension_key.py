#!/usr/bin/env python3
"""Sinh (một lần) cặp khóa RSA để GHIM ID của tiện ích khi nạp "load unpacked".

- Khóa công khai (DER base64) ghi vào trường ``key`` của ``extension/manifest.json``; ID tiện ích = 128 bit đầu của SHA-256
  khóa đó, đổi sang bảng chữ a-p (đúng cách Chrome tính). Nhờ vậy registry policy trỏ đúng tiện ích dù nạp từ thư mục nào.
- Khóa BÍ MẬT lưu ở NGOÀI repo (mặc định ``~/.chotto-dev/extension-key.pem``, quyền chỉ chủ sở hữu trên POSIX) và
  ``*.pem`` nằm trong ``.gitignore``. Demo không cần nó (chỉ cần để đóng gói .crx về sau).

Ví dụ:
  python tools/gen_extension_key.py            # nếu manifest đã có ``key`` thì chỉ in ID
  python tools/gen_extension_key.py --force    # tạo lại (ID đổi, policy cũ mất hiệu lực)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MANIFEST: Final[Path] = ROOT / "extension" / "manifest.json"
DEFAULT_PEM: Final[Path] = Path.home() / ".chotto-dev" / "extension-key.pem"


def extension_id_from_key(key_b64: str) -> str:
    """ID tiện ích (32 ký tự a-p) tính từ trường ``key`` của manifest.

    Raises:
        ValueError: ``key`` không phải base64 hợp lệ.
    """
    der = base64.b64decode(key_b64, validate=True)
    digest = hashlib.sha256(der).hexdigest()[:32]
    return "".join(chr(ord("a") + int(ch, 16)) for ch in digest)


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="tạo khóa mới kể cả khi manifest đã có key")
    parser.add_argument("--pem", type=Path, default=DEFAULT_PEM, help="nơi lưu khóa bí mật (ngoài repo)")
    args = parser.parse_args(argv)

    manifest = json.loads(MANIFEST.read_text("utf-8"))
    if "key" in manifest and not args.force:
        print(f"Manifest đã ghim khóa. ID tiện ích: {extension_id_from_key(manifest['key'])}")
        return 0
    pem_path: Path = args.pem.resolve()
    if ROOT in pem_path.parents:
        print("Từ chối: khóa bí mật không được nằm trong repo.", file=sys.stderr)
        return 2
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem_path.parent.mkdir(parents=True, exist_ok=True)
    pem_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    if os.name == "posix":
        pem_path.chmod(0o600)
    der = private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    manifest["key"] = base64.b64encode(der).decode("ascii")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"Đã ghim khóa. ID tiện ích: {extension_id_from_key(manifest['key'])}\nKhóa bí mật: {pem_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
