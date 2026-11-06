#!/usr/bin/env python3
"""Tạo các gói để đặt trên trang tải (thư mục ``downloads/``), mỗi gói kèm file hướng dẫn song ngữ Anh/Việt.

- ``downloads/CHOTTO-Windows.zip``: ``CHOTTO-Setup.exe`` + ``README.txt`` (cần chạy ``packaging\\build_windows.bat`` trước).
- ``downloads/CHOTTO-macOS.zip``: ``CHOTTO-macOS.dmg`` + ``README.txt`` (cần build ``dist/CHOTTO.app`` trên Mac trước;
  xem ``packaging/macos_setup.py``).
- ``downloads/chotto-extension-chrome.zip``: các file tiện ích (``manifest.json`` ở gốc) + ``README.txt``.
- ``downloads/CHOTTO-Android.zip``: ``CHOTTO-Android-beta.apk`` + ``README.txt`` (cần build trước trong ``android/``:
  ``gradlew assembleRelease``; APK ký bằng khóa debug, cài thẳng được, chưa lên Google Play).

Nội dung hướng dẫn nằm ở ``packaging/guides/*.txt``.
Dùng: python tools/build_downloads.py [windows] [macos] [extension] [android]   (không ghi gì = windows + extension)
"""
from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chotto import __version__  # noqa: E402

DOWNLOADS: Final[Path] = ROOT / "downloads"
GUIDES: Final[Path] = ROOT / "packaging" / "guides"


def _guide(name: str) -> bytes:
    """Nội dung hướng dẫn, thêm BOM UTF-8 để Notepad hiển thị đúng tiếng Việt."""
    data = (GUIDES / name).read_bytes()
    bom = bytes([0xEF, 0xBB, 0xBF])
    return data if data.startswith(bom) else bom + data


def _write(zip_path: Path, entries: dict[str, bytes]) -> None:
    """Ghi ``entries`` (tên trong zip -> nội dung) thành ``zip_path``."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    print(f"Đã tạo {zip_path.relative_to(ROOT)} ({zip_path.stat().st_size} byte, {len(entries)} file)")


def build_windows() -> None:
    """Gói Windows: bộ cài + hướng dẫn."""
    setup = ROOT / "dist" / "CHOTTO-Setup.exe"
    if not setup.exists():
        raise SystemExit("Chưa có dist\\CHOTTO-Setup.exe. Chạy packaging\\build_windows.bat trước.")
    _write(DOWNLOADS / "CHOTTO-Windows.zip", {
        "CHOTTO-Setup.exe": setup.read_bytes(),
        "README.txt": _guide("windows.txt"),
    })


def build_macos() -> None:
    """Gói macOS: ảnh đĩa .dmg (CHOTTO.app + lối tắt Applications) + hướng dẫn. Chỉ chạy được trên Mac."""
    import shutil
    import tempfile

    app = ROOT / "dist" / "CHOTTO.app"
    if sys.platform != "darwin":
        raise SystemExit("Gói macOS cần chạy trên Mac (dùng hdiutil).")
    if not app.is_dir():
        raise SystemExit("Chưa có dist/CHOTTO.app. Build bằng packaging/macos_setup.py py2app và ký trước.")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        stage.mkdir()
        shutil.copytree(app, stage / "CHOTTO.app", symlinks=True)
        (stage / "Applications").symlink_to("/Applications")
        dmg = Path(tmp) / "CHOTTO-macOS.dmg"
        subprocess.run(["hdiutil", "create", "-volname", "CHOTTO", "-srcfolder", str(stage), "-ov",
                        "-format", "UDZO", str(dmg)], check=True, stdout=subprocess.DEVNULL)
        _write(DOWNLOADS / "CHOTTO-macOS.zip", {
            "CHOTTO-macOS.dmg": dmg.read_bytes(),
            "README.txt": _guide("macos.txt"),
        })


def build_extension() -> None:
    """Gói tiện ích: dựng lại bản Chrome rồi thêm hướng dẫn vào gốc gói."""
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_extension.py")], check=True, stdout=subprocess.DEVNULL)
    source = ROOT / "dist" / f"chotto-extension-chrome-{__version__}.zip"
    with zipfile.ZipFile(source) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    if "manifest.json" not in entries:
        raise SystemExit("Gói tiện ích không có manifest.json ở gốc.")
    entries["README.txt"] = _guide("extension.txt")
    _write(DOWNLOADS / "chotto-extension-chrome.zip", entries)


def build_android() -> None:
    """Gói Android (beta): APK release + hướng dẫn."""
    apk = ROOT / "android" / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk"
    if not apk.exists():
        raise SystemExit("Chưa có app-release.apk. Trong thư mục android/ chạy: gradlew assembleRelease")
    _write(DOWNLOADS / "CHOTTO-Android.zip", {
        "CHOTTO-Android-beta.apk": apk.read_bytes(),
        "README.txt": _guide("android.txt"),
    })


def main() -> None:
    """Tạo các gói được chỉ định (mặc định: Windows + tiện ích, như trước)."""
    builders = {"windows": build_windows, "macos": build_macos, "extension": build_extension, "android": build_android}
    targets = sys.argv[1:] or ["windows", "extension"]
    unknown = [t for t in targets if t not in builders]
    if unknown:
        raise SystemExit(f"Không biết gói: {', '.join(unknown)}. Chọn trong: {', '.join(builders)}")
    for target in targets:
        builders[target]()


if __name__ == "__main__":
    main()
