"""Windows: đăng ký CHOTTO làm trình mở link (HKCU, không cần Admin), chuyển tiếp sang trình duyệt thật, tự khởi
động agent và nhận diện link có đến từ Zalo không.

Anti-Loop: trình duyệt đích lấy theo ProgId đã lưu lúc cài; mọi ứng viên trỏ về chính CHOTTO (so đường dẫn file
thực thi, không so chuỗi con) đều bị loại. ``winreg``/``ctypes.windll`` chỉ được nạp bên trong hàm, nên mô-đun vẫn
nhập được trên macOS/Linux (``split_windows_command`` thuần, có kiểm thử trên mọi máy).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping, MutableMapping
from typing import Any, Final

from .common import (
    APP_NAME,
    MAX_ANCESTORS,
    Caller,
    PlatformSetupError,
    build_browser_argv,
    decide_from_evidence,
    default_argv,
    is_self,
    main_script,
    python_launcher,
)

__all__ = [
    "APP_KEY",
    "PROGID",
    "agent_argv",
    "detect_caller",
    "disable_autostart",
    "enable_autostart",
    "install",
    "is_default_handler",
    "open_url",
    "our_command",
    "running_process_names",
    "spawn_agent",
    "split_windows_command",
    "ui_host_argv",
    "uninstall",
]

_LOG = logging.getLogger("chotto.platforms")

PROGID: Final[str] = "ChottoURL"
APP_KEY: Final[str] = r"Software\Clients\StartMenuInternet\CHOTTO"
_URL_ASSOC: Final[str] = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\{scheme}"
_RUN_KEY: Final[str] = r"Software\Microsoft\Windows\CurrentVersion\Run"
_DETACHED_PROCESS: Final[int] = 0x00000008
_CREATE_NEW_PROCESS_GROUP: Final[int] = 0x00000200
_CREATE_NO_WINDOW: Final[int] = 0x08000000
_BROWSER_PREFERENCE: Final[tuple[str, ...]] = ("chrome", "edge", "coccoc", "cốc cốc", "firefox", "brave", "opera")
_FALLBACKS: Final[tuple[str, ...]] = (
    r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%LOCALAPPDATA%\CocCoc\Browser\Application\browser.exe",
    r"%ProgramFiles%\CocCoc\Browser\Application\browser.exe",
    r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
    r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
    r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
)


# ---------------- tách lệnh (thuần) ----------------
def split_windows_command(command: str) -> list[str]:
    """Tách chuỗi lệnh Windows thành argv theo đúng quy tắc của ``CommandLineToArgvW``.

    Phần tử đầu (đường dẫn chương trình) chỉ dùng ngoặc kép để bao, không xử lý ``\\``; các phần tử
    sau theo quy tắc ``2n`` / ``2n+1`` dấu ``\\`` trước ``"`` của Microsoft C runtime.
    """
    args: list[str] = []
    text = command.strip()
    length = len(text)
    index = 0
    if index < length and text[index] == '"':
        end = text.find('"', index + 1)
        end = length if end == -1 else end
        args.append(text[index + 1 : end])
        index = end + 1
    else:
        end = index
        while end < length and text[end] not in " \t":
            end += 1
        args.append(text[index:end])
        index = end
    while True:
        while index < length and text[index] in " \t":
            index += 1
        if index >= length:
            break
        buffer: list[str] = []
        in_quotes = False
        while index < length:
            char = text[index]
            if char == "\\":
                run_end = index
                while run_end < length and text[run_end] == "\\":
                    run_end += 1
                count = run_end - index
                if run_end < length and text[run_end] == '"':
                    buffer.append("\\" * (count // 2))
                    if count % 2:
                        buffer.append('"')
                        index = run_end + 1
                    else:
                        index = run_end
                else:
                    buffer.append("\\" * count)
                    index = run_end
            elif char == '"':
                if in_quotes and index + 1 < length and text[index + 1] == '"':
                    buffer.append('"')
                    index += 2
                else:
                    in_quotes = not in_quotes
                    index += 1
            elif char in " \t" and not in_quotes:
                break
            else:
                buffer.append(char)
                index += 1
        args.append("".join(buffer))
    return args if args and args[0] else []


# ---------------- khởi chạy CHOTTO ----------------
def our_command() -> str:
    """Lệnh mà Windows dùng để gọi CHOTTO với một URL (ghi vào registry)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    return f'"{python_launcher()}" "{main_script()}" "%1"'


def agent_argv() -> list[str]:
    """Lệnh khởi động agent thường trú."""
    return default_argv("agent")


def ui_host_argv() -> list[str]:
    """Lệnh chạy tiến trình giao diện HTML."""
    return default_argv("ui-host")


def spawn_agent(argv: list[str]) -> None:
    """Khởi động agent tách rời, không hiện cửa sổ console.

    Raises:
        OSError: Không chạy được lệnh.
    """
    subprocess.Popen(argv, creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP | _CREATE_NO_WINDOW,
                     close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def enable_autostart(argv: list[str]) -> None:
    """Ghi khóa ``Run`` trong HKCU để agent tự chạy khi đăng nhập.

    Raises:
        PlatformSetupError: Không ghi được registry.
    """
    import winreg

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(argv))
    except OSError as exc:
        raise PlatformSetupError(f"Không ghi được khóa tự khởi động: {exc}") from exc


def disable_autostart() -> None:
    """Gỡ khóa ``Run``; không có thì bỏ qua."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except OSError:
        pass


# ---------------- registry ----------------
def _reg_read(root: int, path: str, name: str = "", flags: int = 0) -> str | None:
    """Đọc một giá trị chuỗi trong registry; không có thì ``None``."""
    import winreg

    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | flags) as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value) if isinstance(value, str) and value else None


def _user_choice_progid(scheme: str = "https") -> str | None:
    """ProgId trình duyệt mặc định hiện tại (ưu tiên ``UserChoiceLatest`` của Windows 11 mới)."""
    import winreg

    base = _URL_ASSOC.format(scheme=scheme)
    # Windows 11 mới ghi lựa chọn vào khóa con ``UserChoiceLatest\ProgId`` (giá trị ``ProgId``); ``UserChoice`` cũ có
    # thể vẫn còn trình duyệt trước đó (ví dụ ``MSEdgeHTM``) nên chỉ dùng khi không có hai khóa mới.
    for sub in ("UserChoiceLatest\\ProgId", "UserChoiceLatest", "UserChoice"):
        progid = _reg_read(winreg.HKEY_CURRENT_USER, base + "\\" + sub, "ProgId")
        if progid:
            return progid
    return None


def _progid_command(progid: str) -> str | None:
    """Lệnh ``shell\\open\\command`` của một ProgId (khung nhìn gộp HKCU + HKLM)."""
    import winreg

    return _reg_read(winreg.HKEY_CLASSES_ROOT, progid + r"\shell\open\command")


def _start_menu_clients() -> Iterator[tuple[str, str]]:
    """Các trình duyệt đã đăng ký trong ``StartMenuInternet`` (tên khóa, lệnh mở), trừ CHOTTO."""
    import winreg

    locations = (
        (winreg.HKEY_CURRENT_USER, 0),
        (winreg.HKEY_LOCAL_MACHINE, 0),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
    )
    for root, flags in locations:
        try:
            with winreg.OpenKey(root, r"Software\Clients\StartMenuInternet", 0, winreg.KEY_READ | flags) as key:
                index = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, index)
                    except OSError:
                        break
                    index += 1
                    if name.upper() == APP_NAME:
                        continue
                    command = _reg_read(root, rf"Software\Clients\StartMenuInternet\{name}\shell\open\command",
                                        flags=flags)
                    if command:
                        yield name, command
        except OSError:
            continue


# ---------------- trình duyệt thật ----------------
def _preference_rank(name: str) -> int:
    """Thứ tự ưu tiên khi phải tự chọn trình duyệt."""
    lowered = name.lower()
    for rank, keyword in enumerate(_BROWSER_PREFERENCE):
        if keyword in lowered:
            return rank
    return len(_BROWSER_PREFERENCE)


def _usable_argv(command: str) -> list[str] | None:
    """Argv mẫu nếu lệnh trỏ tới một file thực thi tồn tại và không phải CHOTTO."""
    args = split_windows_command(command)
    if not args:
        return None
    args[0] = os.path.expandvars(args[0])
    if not os.path.isfile(args[0]) or is_self(args):
        return None
    return args


def _candidates(cfg: Mapping[str, Any]) -> Iterator[list[str]]:
    """Các argv mẫu của trình duyệt thật theo thứ tự ưu tiên (đã loại CHOTTO)."""
    commands: list[str] = []
    saved_progid = str(cfg.get("browser_progid") or "")
    if saved_progid and saved_progid != PROGID:
        command = _progid_command(saved_progid)
        if command:
            commands.append(command)
    if cfg.get("browser_command"):
        commands.append(str(cfg["browser_command"]))
    current = _user_choice_progid()
    if current and current != PROGID:
        command = _progid_command(current)
        if command:
            commands.append(command)
    clients = sorted(_start_menu_clients(), key=lambda item: _preference_rank(item[0]))
    commands.extend(command for _, command in clients)
    commands.extend(f'"{os.path.expandvars(path)}"' for path in _FALLBACKS)
    seen: set[str] = set()
    for command in commands:
        argv = _usable_argv(command)
        if argv is None:
            continue
        key = os.path.normcase(argv[0])
        if key in seen and len(argv) == 1:
            continue
        seen.add(key)
        yield argv


def open_url(url: str, cfg: Mapping[str, Any]) -> bool:
    """Mở ``url`` bằng trình duyệt thật đầu tiên khởi chạy được."""
    for template in _candidates(cfg):
        argv = build_browser_argv(template, url)
        try:
            subprocess.Popen(argv, creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP, close_fds=True)
        except OSError:
            _LOG.warning("Không khởi chạy được %s, thử trình duyệt kế tiếp", template[0], exc_info=True)
            continue
        return True
    return False


# ---------------- đăng ký / gỡ ----------------
def is_default_handler() -> bool:
    """CHOTTO có đang là trình mở link https mặc định không.

    Gỡ đăng ký chỉ xóa khóa ChottoURL; lựa chọn người dùng (UserChoice) vẫn trỏ tới nó cho tới khi họ chọn trình
    duyệt khác. Không còn lệnh mở thì CHOTTO không còn là trình xử lý, dù UserChoice còn ghi tên.
    """
    return _user_choice_progid("https") == PROGID and bool(_progid_command(PROGID))


def handler_released() -> bool | None:
    """CHOTTO hết nhận link: lệnh mở của ProgId CHOTTO (dùng chung cho http và https) đã bị xóa.

    Chỉ "chắc chắn không có khóa" mới là đã nhả; còn khóa (gỡ chưa xong) là chưa; đọc registry lỗi là không biết.
    """
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, PROGID + r"\shell\open\command"):
            return False
    except FileNotFoundError:
        return True
    except OSError:
        return None


def install(cfg: MutableMapping[str, Any]) -> str:
    """Đăng ký CHOTTO trong HKCU, ghi nhớ trình duyệt thật vào ``cfg`` và mở trang chọn ứng dụng mặc định.

    Raises:
        PlatformSetupError: Không ghi được registry.
    """
    import winreg

    current = _user_choice_progid()
    if current and current != PROGID:
        cfg["browser_progid"] = current
        command = _progid_command(current)
        if command and _usable_argv(command) is not None:
            cfg["browser_command"] = command
    if not cfg.get("browser_command"):
        first = next(_candidates(cfg), None)
        if first is not None:
            cfg["browser_command"] = subprocess.list2cmdline(first) + ' "%1"'

    hive = winreg.HKEY_CURRENT_USER

    def set_value(path: str, name: str, value: str) -> None:
        with winreg.CreateKey(hive, path) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    icon = f"{sys.executable},0"
    try:
        set_value(rf"Software\Classes\{PROGID}", "", "CHOTTO URL")
        set_value(rf"Software\Classes\{PROGID}", "FriendlyTypeName", "CHOTTO")
        try:
            with winreg.OpenKey(hive, rf"Software\Classes\{PROGID}", 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, "URL Protocol")     # bản cũ biến ProgId thành scheme gọi được từ web
        except OSError:
            pass
        set_value(rf"Software\Classes\{PROGID}\DefaultIcon", "", icon)
        set_value(rf"Software\Classes\{PROGID}\shell\open\command", "", our_command())
        set_value(APP_KEY, "", APP_NAME)
        set_value(APP_KEY + r"\DefaultIcon", "", icon)
        set_value(APP_KEY + r"\shell\open\command", "", our_command().replace(' "%1"', ""))
        set_value(APP_KEY + r"\Capabilities", "ApplicationName", APP_NAME)
        set_value(APP_KEY + r"\Capabilities", "ApplicationDescription", "Khoan đã! Kiểm tra link Zalo trước khi mở")
        set_value(APP_KEY + r"\Capabilities\URLAssociations", "http", PROGID)
        set_value(APP_KEY + r"\Capabilities\URLAssociations", "https", PROGID)
        set_value(r"Software\RegisteredApplications", APP_NAME, APP_KEY + r"\Capabilities")
    except OSError as exc:
        raise PlatformSetupError(f"Không ghi được registry: {exc}") from exc
    for target in (f"ms-settings:defaultapps?registeredAppUser={APP_NAME}", "ms-settings:defaultapps"):
        try:
            os.startfile(target)
            break
        except OSError:
            continue
    if not cfg.get("browser_command"):
        return ("Đã đăng ký CHOTTO nhưng KHÔNG tìm thấy trình duyệt thật để chuyển tiếp. Hãy cài Chrome, Edge, "
                "Cốc Cốc hoặc Firefox rồi bấm cài đặt lại.")
    return ("Đã đăng ký CHOTTO. Windows không cho phần mềm tự đặt mặc định: trong cửa sổ Cài đặt vừa mở, "
            "đặt CHOTTO cho HTTP và HTTPS.")


def uninstall(cfg: Mapping[str, Any]) -> str:
    """Xóa mọi khóa registry CHOTTO đã tạo trong HKCU."""
    import winreg

    hive = winreg.HKEY_CURRENT_USER

    def remove_tree(path: str) -> None:
        try:
            with winreg.OpenKey(hive, path) as key:
                children: list[str] = []
                index = 0
                while True:
                    try:
                        children.append(winreg.EnumKey(key, index))
                    except OSError:
                        break
                    index += 1
        except OSError:
            return
        for child in children:
            remove_tree(path + "\\" + child)
        try:
            winreg.DeleteKey(hive, path)
        except OSError:
            _LOG.warning("Không xóa được khóa registry %s", path)

    remove_tree(rf"Software\Classes\{PROGID}")
    remove_tree(APP_KEY)
    try:
        with winreg.OpenKey(hive, r"Software\RegisteredApplications", 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except OSError:
        pass
    return "Đã gỡ đăng ký. Hãy chọn lại trình duyệt mặc định trong Cài đặt Windows."


# ---------------- nhận diện nguồn gọi ----------------
def _evidence() -> tuple[list[str], str | None]:
    """Thu thập (chuỗi tổ tiên đã kiểm chứng thời điểm tạo, tiến trình foreground).

    ``CreateToolhelp32Snapshot`` cho chuỗi tiến trình cha, có kiểm tra thời điểm tạo để chống tái sử dụng PID;
    ``GetForegroundWindow`` cho ứng dụng người dùng vừa bấm.

    Raises:
        OSError: Không chụp được danh sách tiến trình.
    """
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    invalid_handle = wintypes.HANDLE(-1).value
    th32cs_snapprocess = 0x00000002
    process_query_limited_information = 0x1000

    snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
    if not snapshot or snapshot == invalid_handle:
        raise ctypes.WinError(ctypes.get_last_error())
    processes: dict[int, tuple[int, str]] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            processes[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), entry.szExeFile.lower())
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)

    def creation_time(pid: int) -> int | None:
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return None
        try:
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                            ctypes.byref(kernel), ctypes.byref(user)):
                return None
            return (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        finally:
            kernel32.CloseHandle(handle)

    ancestors: list[str] = []
    pid = os.getpid()
    child_created = creation_time(pid)
    for _ in range(MAX_ANCESTORS):
        parent = processes.get(pid, (0, ""))[0]
        if not parent or parent not in processes:
            break
        parent_created = creation_time(parent)
        # PID cha có thể đã bị cấp lại cho tiến trình khác sinh SAU tiến trình con: dừng chuỗi.
        if parent_created is None or (child_created is not None and parent_created > child_created):
            break
        ancestors.append(processes[parent][1])
        pid, child_created = parent, parent_created

    foreground: str | None = None
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        fg_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(fg_pid))
        foreground = processes.get(int(fg_pid.value), (0, ""))[1] or None
    return ancestors, foreground


def running_process_names() -> set[str]:
    """Tên file (chữ thường) của mọi tiến trình đang chạy; rỗng nếu không đọc được."""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)                 # TH32CS_SNAPPROCESS
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        return set()
    names: set[str] = set()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            names.add(entry.szExeFile.lower())
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return names


def detect_caller(cfg: Mapping[str, Any]) -> Caller:
    """Nhận diện nguồn gọi theo tiến trình cha và cửa sổ foreground.

    Raises:
        OSError: Không đọc được danh sách tiến trình.
    """
    ancestors, foreground = _evidence()
    zalo = {str(p).lower() for p in cfg["zalo_processes"]}
    own = {os.path.basename(sys.executable).lower(), "chotto.exe", "python.exe", "pythonw.exe"}
    return decide_from_evidence(ancestors, foreground, zalo, own)
