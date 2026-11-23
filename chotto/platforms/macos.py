"""macOS: đặt CHOTTO.app làm trình mở link qua LaunchServices, chuyển tiếp sang trình duyệt thật, tự khởi động
agent bằng LaunchAgent và nhận diện link có đến từ Zalo không (``lsappinfo``)."""
from __future__ import annotations

import logging
import os
import plistlib
import re
import subprocess
import sys
from collections.abc import Iterator, Mapping, MutableMapping
from pathlib import Path
from typing import Any, Final

from .common import (
    MAX_ANCESTORS,
    OWN_BUNDLE,
    Caller,
    PlatformSetupError,
    decide_from_evidence,
    default_argv,
    spawn_in_new_session,
)

__all__ = [
    "agent_argv",
    "detect_caller",
    "disable_autostart",
    "enable_autostart",
    "install",
    "is_default_handler",
    "open_url",
    "spawn_agent",
    "ui_host_argv",
    "uninstall",
]

_LOG = logging.getLogger("chotto.platforms")

_LAUNCH_AGENT_LABEL: Final[str] = "vn.chotto.agent"
_LS_PLIST: Final[str] = "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
_LSAPPINFO_TIMEOUT_S: Final[float] = 0.75
_SAFE_BUNDLE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9.-]+$")
_FALLBACKS: Final[tuple[tuple[str, str], ...]] = (
    ("com.google.chrome", "/Applications/Google Chrome.app"),
    ("com.apple.safari", "/Applications/Safari.app"),
    ("org.mozilla.firefox", "/Applications/Firefox.app"),
    ("com.microsoft.edgemac", "/Applications/Microsoft Edge.app"),
    ("com.coccoc.coccoc", "/Applications/CocCoc.app"),
    ("com.brave.browser", "/Applications/Brave Browser.app"),
)


# ---------------- khởi chạy CHOTTO ----------------
def agent_argv() -> list[str]:
    """Lệnh khởi động agent; bản .app đi qua LaunchServices để chỉ có một CHOTTO.app (nhận được Apple Event mở link)."""
    if getattr(sys, "frozen", False):
        return ["/usr/bin/open", "-g", "-b", OWN_BUNDLE, "--args", "agent"]
    return default_argv("agent")


def ui_host_argv() -> list[str]:
    """Lệnh chạy tiến trình giao diện HTML.

    py2app: ``sys.executable`` là trình thông dịch trần (không chạy main.py); phải gọi bộ khởi chạy của .app.
    """
    if getattr(sys, "frozen", False):
        return [str(Path(sys.executable).with_name(Path(sys.executable).parent.parent.parent.stem)), "ui-host"]
    return default_argv("ui-host")


def spawn_agent(argv: list[str]) -> None:
    """Khởi động agent tách rời.

    Raises:
        OSError: Không chạy được lệnh.
    """
    spawn_in_new_session(argv)


def _launch_agent_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LAUNCH_AGENT_LABEL}.plist"


def enable_autostart(argv: list[str]) -> None:
    """Ghi LaunchAgent để agent tự chạy khi đăng nhập.

    Raises:
        PlatformSetupError: Không ghi được plist.
    """
    path = _launch_agent_plist()
    payload = {"Label": _LAUNCH_AGENT_LABEL, "ProgramArguments": argv, "RunAtLoad": True, "ProcessType": "Interactive"}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(plistlib.dumps(payload))
        os.replace(tmp, path)
    except OSError as exc:
        raise PlatformSetupError(f"Không ghi được {path}: {exc}") from exc


def disable_autostart() -> None:
    """Xóa LaunchAgent; không có thì bỏ qua."""
    try:
        _launch_agent_plist().unlink()
    except FileNotFoundError:
        pass
    except OSError:
        _LOG.warning("Không xóa được LaunchAgent", exc_info=True)


# ---------------- LaunchServices ----------------
def _ls_handlers() -> list[Any]:
    """Danh sách ``LSHandlers`` của LaunchServices.

    Raises:
        OSError, ValueError: Không đọc được plist (``plistlib.InvalidFileException`` là ``ValueError``).
    """
    handlers = plistlib.loads((Path.home() / _LS_PLIST).read_bytes()).get("LSHandlers", [])
    return handlers if isinstance(handlers, list) else []


def _handler_for(handlers: list[Any], scheme: str) -> str:
    """Bundle id (chữ thường) đang xử lý ``scheme``; chưa có thì chuỗi rỗng."""
    for handler in handlers:
        if isinstance(handler, dict) and handler.get("LSHandlerURLScheme") == scheme:
            return str(handler.get("LSHandlerRoleAll") or "").lower()
    return ""


def _current_default_bundle() -> str | None:
    """Bundle id trình duyệt mặc định (bỏ qua CHOTTO)."""
    try:
        handlers = _ls_handlers()
    except (OSError, ValueError):
        return None
    for scheme in ("https", "http"):
        bundle = _handler_for(handlers, scheme)
        if bundle and bundle != OWN_BUNDLE:
            return bundle
    return None


def _set_url_handler(bundle: str) -> bool:
    """Đặt ``bundle`` làm trình xử lý http/https qua LaunchServices (macOS hiện hộp thoại xác nhận).

    Không chờ kết quả: hộp thoại nằm ở tiến trình ``osascript``. ``False`` nếu không chạy được lệnh.
    """
    if not _SAFE_BUNDLE.match(bundle):          # bundle id đi vào mã JavaScript: chỉ nhận ký tự an toàn
        _LOG.error("Bundle id không hợp lệ")
        return False
    script = ('ObjC.import("CoreServices"); '
              f'$.LSSetDefaultHandlerForURLScheme($("http"), $("{bundle}")); '
              f'$.LSSetDefaultHandlerForURLScheme($("https"), $("{bundle}"));')
    try:
        subprocess.Popen(["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        _LOG.warning("Không gọi được LaunchServices để đặt trình xử lý link", exc_info=True)
        return False
    return True


def is_default_handler() -> bool:
    """CHOTTO có đang là trình mở link https mặc định không.

    Raises:
        OSError, ValueError: Không đọc được cấu hình LaunchServices.
    """
    return _handler_for(_ls_handlers(), "https") == OWN_BUNDLE


# ---------------- trình duyệt thật ----------------
def _candidates(cfg: Mapping[str, Any]) -> Iterator[str]:
    """Các bundle id trình duyệt thật theo thứ tự ưu tiên (đã loại CHOTTO)."""
    seen: set[str] = set()
    ordered = [str(cfg.get("browser_bundle_id") or ""), _current_default_bundle() or ""]
    ordered += [bundle for bundle, path in _FALLBACKS if os.path.exists(path)]
    for bundle in ordered:
        bundle = bundle.lower()
        if bundle and bundle != OWN_BUNDLE and bundle not in seen:
            seen.add(bundle)
            yield bundle


def open_url(url: str, cfg: Mapping[str, Any]) -> bool:
    """Mở ``url`` bằng ``open -b <bundle>``; kiểm tra mã thoát, thử bundle kế tiếp nếu lỗi."""
    for bundle in _candidates(cfg):
        try:
            completed = subprocess.run(["open", "-b", bundle, url], capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            _LOG.warning("Không chạy được 'open -b %s'", bundle, exc_info=True)
            continue
        if completed.returncode == 0:
            return True
        _LOG.warning("'open -b %s' trả mã %s", bundle, completed.returncode)
    return False


# ---------------- đăng ký / gỡ ----------------
def install(cfg: MutableMapping[str, Any]) -> str:
    """Ghi nhớ trình duyệt thật hiện tại vào ``cfg`` rồi xin đặt CHOTTO làm trình mở link."""
    cfg["browser_bundle_id"] = _current_default_bundle() or next(
        (bundle for bundle, path in _FALLBACKS if os.path.exists(path)), "com.apple.safari"
    )
    # Danh sách "Trình duyệt web mặc định" của Cài đặt Hệ thống không liệt kê CHOTTO (không khai báo kiểu tài liệu
    # HTML), nên gọi thẳng LaunchServices: macOS tự hiện hộp thoại hỏi người dùng có đổi sang CHOTTO không.
    if not _set_url_handler(OWN_BUNDLE):
        return "Không đặt được tự động. Hãy đặt CHOTTO làm trình duyệt mặc định trong Cài đặt Hệ thống."
    return "macOS sẽ hỏi bạn có đổi trình duyệt mặc định sang CHOTTO không: hãy chọn \"Dùng CHOTTO\"."


def uninstall(cfg: Mapping[str, Any]) -> str:
    """Trả trình mở link về trình duyệt đã ghi nhớ lúc cài (nếu CHOTTO đang là mặc định)."""
    try:
        is_default = is_default_handler()
    except (OSError, ValueError):
        is_default = False
    if is_default:
        bundle = next(_candidates(cfg), "com.apple.safari")
        if _set_url_handler(bundle):
            return "macOS sẽ hỏi bạn có đổi trình duyệt mặc định về trình duyệt cũ không: hãy đồng ý."
    return "Hãy chọn lại trình duyệt mặc định trong Cài đặt Hệ thống > Màn hình nền & Dock."


# ---------------- nhận diện nguồn gọi ----------------
def _lsappinfo(*args: str) -> str:
    return subprocess.run(["lsappinfo", *args], capture_output=True, text=True,
                          timeout=_LSAPPINFO_TIMEOUT_S, check=False).stdout


def _front_bundle() -> str | None:
    """Bundle id ứng dụng phía trước, bỏ qua chính CHOTTO; lỗi/timeout trả ``None``.

    macOS đưa CHOTTO lên trước khi giao link, nên ``lsappinfo front`` luôn là CHOTTO. ``visibleProcessList``
    xếp ứng dụng từ trước ra sau: ứng dụng đầu tiên không phải CHOTTO là nơi người dùng vừa bấm link.
    """
    try:
        asns = re.findall(r"ASN:0x[0-9a-f]+-0x[0-9a-f]+", _lsappinfo("visibleProcessList"))
        for asn in asns[:MAX_ANCESTORS]:
            match = re.search(r'="([^"]+)"', _lsappinfo("info", "-only", "bundleid", asn))
            if match and match.group(1).lower() != OWN_BUNDLE:
                return match.group(1).lower()
    except (OSError, subprocess.SubprocessError):
        _LOG.warning("lsappinfo lỗi", exc_info=True)
    return None


def detect_caller(cfg: Mapping[str, Any]) -> Caller:
    """Nhận diện nguồn gọi theo ứng dụng phía trước."""
    zalo_bundles = {str(b).lower() for b in cfg["zalo_bundle_ids"]}
    return decide_from_evidence([], _front_bundle(), zalo_bundles, {OWN_BUNDLE})
