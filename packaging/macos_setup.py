"""Build CHOTTO.app cho macOS (chạy từ thư mục gốc dự án):
    pip install -r requirements.txt && python packaging/macos_setup.py py2app
Info.plist khai báo CHOTTO xử lý http/https để xuất hiện trong "Trình duyệt web mặc định"."""
import sys
from typing import Any

from setuptools import setup

if sys.version_info < (3, 11):
    raise SystemExit("CHOTTO cần Python 3.11 trở lên.")

VERSION = "1.5.0"

# Python dựng sẵn (uv/python-build-standalone) biên dịch zlib vào lõi nên ``zlib.__file__`` không tồn tại,
# trong khi py2app luôn chép file đó vào .app. Đưa cho nó một file rỗng; zlib thật vẫn nằm trong libpython.
import tempfile
import zlib

if not hasattr(zlib, "__file__"):
    _stub = tempfile.NamedTemporaryFile(prefix="zlib_builtin_", suffix=".so", delete=False)
    _stub.close()
    zlib.__file__ = _stub.name  # type: ignore[attr-defined]

# Không khai báo CFBundleDocumentTypes: CHOTTO chỉ nhận link qua Apple Event kAEGetURL
# (::tk::mac::LaunchURL). Khai báo kiểu tài liệu HTML mà không xử lý OpenDocument sẽ khiến
# file .html/.webloc mở bằng CHOTTO bị nuốt im lặng.
PLIST = {
    "CFBundleName": "CHOTTO",
    "CFBundleDisplayName": "CHOTTO",
    "CFBundleIdentifier": "vn.chotto.app",
    "CFBundleVersion": VERSION,
    "CFBundleShortVersionString": VERSION,
    "LSMinimumSystemVersion": "11.0",
    "NSHighResolutionCapable": True,
    "LSUIElement": True,                         # không hiện icon Dock khi chạy nền
    "CFBundleURLTypes": [{"CFBundleURLName": "Web URL", "CFBundleURLSchemes": ["http", "https"]}],
}

# Khai báo kiểu Any: stub của setuptools chỉ cho phép Mapping[str, Mapping[str, str]],
# trong khi py2app cần giá trị là dict/list/bool.
OPTIONS: dict[str, Any] = {
    "py2app": {
        "plist": PLIST,
        "iconfile": "packaging/chotto.icns",
        "packages": ["chotto", "webview"],       # kéo theo chotto/data và chotto/web (giao diện HTML, font)
        "includes": ["tkinter"],
        "argv_emulation": False,   # phải tắt: link http(s) đến qua Apple Event (::tk::mac::LaunchURL), không qua argv
    }
}

setup(
    name="CHOTTO",
    version=VERSION,
    app=["main.py"],
    packages=[],            # tắt auto-discovery của setuptools (thư mục gốc có nhiều package: chotto, tests, packaging)
    options=OPTIONS,
)


def _bundle_tcl_tk() -> None:
    """py2app không bó Tcl/Tk 9 của Python dựng sẵn (uv): chép thư viện + script vào ``Resources/lib`` của .app."""
    import shutil
    from pathlib import Path

    src = Path(sys.base_prefix) / "lib"
    dst = Path("dist/CHOTTO.app/Contents/Resources/lib")
    if not (src / "libtcl9tk9.0.dylib").exists() or not dst.is_dir():
        return
    for name in ("libtcl9.0.dylib", "libtcl9tk9.0.dylib"):
        shutil.copy2(src / name, dst / name)
    for name in ("tcl9.0", "tk9.0", "tcl9"):
        if (src / name).is_dir():
            shutil.copytree(src / name, dst / name, dirs_exist_ok=True)


if "py2app" in sys.argv:
    _bundle_tcl_tk()
