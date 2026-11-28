"""AI Local cho nhân vật taskbar: tải ``llama-server`` (llama.cpp) + model GGUF và chạy 100% trên máy, không cần Python/Ollama.

Thư mục: ``data_dir()/local_ai/{bin,models}``. Hai tiến trình dùng mô-đun này:

- Tiến trình giao diện (``webhost.AppApi``): tải engine/model (``DOWNLOADS``), xóa model, báo trạng thái.
- Agent (luồng nhân vật): ``SERVER.ensure`` khởi chạy ``llama-server.exe`` ẩn trên ``127.0.0.1:<cổng trống>`` khi hỏi đáp ở chế độ
  ``local``, tự tắt sau ``IDLE_S`` giây không dùng, khi đổi chế độ hoặc khi agent thoát. PID ghi ở ``server.json`` để tiến trình
  giao diện xóa model đang chạy thì tắt được server (chỉ khi PID đúng là ``llama-server.exe``).

Mọi file tải về đều qua ``.part``, kiểm kích thước + SHA256 (lấy từ API của GitHub / Hugging Face) rồi mới đổi tên.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from ..config import MASCOT_LOCAL_MODELS, data_dir

__all__ = ["CATALOG", "DOWNLOADS", "IDLE_S", "SERVER", "LocalAIError", "LocalModel", "delete_model", "engine_ready",
           "find", "is_downloaded", "model_path", "status"]

_LOG = logging.getLogger("chotto")

# KHÔNG dùng ``releases/latest``: bản đó (``vX.Y.Z``) không kèm gói chạy; gói Windows nằm ở các bản ``bNNNN`` đánh dấu pre-release.
ENGINE_RELEASE_API: Final[str] = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20"
HF_TREE_API: Final[str] = "https://huggingface.co/api/models/{repo}/tree/main"
HF_FILE: Final[str] = "https://huggingface.co/{repo}/resolve/main/{file}"
IDLE_S: Final[float] = 300.0                    # tắt server sau 5 phút không hỏi (giải phóng RAM)
_CHUNK: Final[int] = 1 << 20
_UA: Final[dict[str, str]] = {"User-Agent": "CHOTTO-local-ai"}
_WIN: Final[bool] = sys.platform == "win32"
_MAC: Final[bool] = sys.platform == "darwin"
SUPPORTED: Final[bool] = _WIN or _MAC
_EXE: Final[str] = "llama-server.exe" if _WIN else "llama-server"
_CREATE_NO_WINDOW: Final[int] = 0x08000000
# Windows: không bật cửa sổ console cho tiến trình con. macOS: ``creationflags`` khác 0 là lỗi (0 thì được).
_NO_WINDOW: Final[int] = _CREATE_NO_WINDOW if _WIN else 0


@dataclass(frozen=True)
class LocalModel:
    """Một model GGUF trong danh mục (mô tả từng model ở ``chotto/web/i18n.js``: ``buddy.localDesc.<id>``)."""

    id: str
    name: str
    short: str                 # nhãn ngắn cho nút chọn
    repo: str                  # kho Hugging Face (công khai, không cần đăng nhập)
    file: str
    size_gb: float             # dung lượng tải (xấp xỉ, số thật lấy từ Hugging Face lúc tải)
    ram_gb: float              # RAM trống khuyến nghị
    system_role: bool = True   # Gemma 2 không nhận vai "system": gộp lời nhắc vào câu hỏi
    format: str = "GGUF"
    quant: str = "Q4_K_M"


CATALOG: Final[tuple[LocalModel, ...]] = (
    LocalModel("qwen2.5-0.5b", "Qwen2.5-0.5B-Instruct", "Qwen 0.5B", "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
               "qwen2.5-0.5b-instruct-q4_k_m.gguf", 0.4, 1.0),
    LocalModel("qwen2.5-1.5b", "Qwen2.5-1.5B-Instruct", "Qwen 1.5B", "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
               "qwen2.5-1.5b-instruct-q4_k_m.gguf", 1.1, 2.0),
    LocalModel("qwen2.5-3b", "Qwen2.5-3B-Instruct", "Qwen 3B", "Qwen/Qwen2.5-3B-Instruct-GGUF",
               "qwen2.5-3b-instruct-q4_k_m.gguf", 2.0, 3.5),
    LocalModel("gemma-2-2b", "Gemma-2-2B-it", "Gemma 2B", "bartowski/gemma-2-2b-it-GGUF",
               "gemma-2-2b-it-Q4_K_M.gguf", 1.6, 3.0, system_role=False),
)
assert tuple(m.id for m in CATALOG) == MASCOT_LOCAL_MODELS, "config.MASCOT_LOCAL_MODELS phải khớp CATALOG"


class LocalAIError(Exception):
    """Lỗi có mã ngắn cho giao diện: network | checksum | disk | unsupported | notfound | cancelled | start."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


# ---- đường dẫn ----
_WRITABLE: dict[Path, bool] = {}


def _writable(directory: Path) -> bool:
    if directory not in _WRITABLE:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".write-test"
            probe.write_bytes(b"")
            probe.unlink()
            _WRITABLE[directory] = True
        except OSError:
            _WRITABLE[directory] = False
    return _WRITABLE[directory]


def _root() -> Path:
    """Bản cài (PyInstaller ``--onedir``): ``<thư mục CHOTTO>\\local_ai`` cạnh ``CHOTTO.exe``, để xóa thư mục app hay gỡ cài đặt
    là sạch luôn model + engine. Chạy từ mã nguồn/kiểm thử, hoặc thư mục cài không ghi được (vd. Program Files): ``data_dir()``.
    macOS luôn dùng ``data_dir()``: ghi vào bên trong ``CHOTTO.app`` làm hỏng chữ ký, Gatekeeper có thể chặn app.
    """
    if _WIN and getattr(sys, "frozen", False) and not os.environ.get("CHOTTO_DATA_DIR"):
        beside_app = Path(sys.executable).resolve().parent / "local_ai"
        if _writable(beside_app):
            return beside_app
    return data_dir() / "local_ai"


def bin_dir() -> Path:
    return _root() / "bin"


def models_dir() -> Path:
    return _root() / "models"


def server_exe() -> Path:
    return bin_dir() / _EXE


def engine_ready() -> bool:
    """Đã có ``llama-server.exe`` chưa."""
    return server_exe().is_file()


def find(model_id: str) -> LocalModel | None:
    return next((m for m in CATALOG if m.id == model_id), None)


def model_path(model: LocalModel) -> Path:
    return models_dir() / model.file


def is_downloaded(model_id: str) -> bool:
    """File model đã tải xong và qua kiểm tra (file ``.part`` dở dang không tính)."""
    model = find(model_id)
    return model is not None and model_path(model).is_file()


def arch() -> str:
    """``x64`` | ``arm64`` của máy (Windows: kể cả khi Python x64 chạy giả lập trên máy ARM; macOS: chip Apple là ``arm64``)."""
    machine = (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE") or platform.machine()).lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


# ---- tải về ----
Progress = Callable[[int, int], None]


def _open(url: str, timeout: float = 30.0) -> Any:
    request = urllib.request.Request(url, headers={**_UA, "Accept": "application/json, */*"})
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - chỉ các địa chỉ https cố định ở trên


def _fetch_json(url: str) -> Any:
    try:
        with _open(url) as response:
            return json.loads(response.read(8 << 20).decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise LocalAIError("network", str(exc)) from exc


def _check_space(directory: Path, need: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(directory).free < need + (200 << 20):
        raise LocalAIError("disk", f"cần {need >> 20} MB")


def download_file(url: str, dest: Path, size: int, sha256: str, progress: Progress, cancel: threading.Event) -> None:
    """Tải ``url`` về ``dest`` qua ``dest.part``; chỉ đổi tên khi đúng ``size`` byte và đúng ``sha256``.

    Raises:
        LocalAIError: ``cancelled`` | ``network`` | ``checksum`` | ``disk``.
    """
    _check_space(dest.parent, size)
    part = dest.with_name(dest.name + ".part")
    digest = hashlib.sha256()
    done = 0
    try:
        with _open(url, timeout=60.0) as response, open(part, "wb") as out:
            while True:
                if cancel.is_set():
                    raise LocalAIError("cancelled")
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if done > size:
                    raise LocalAIError("checksum", "lớn hơn kích thước công bố")
                progress(done, size)
        if done != size:
            raise LocalAIError("network" if done < size else "checksum", f"{done}/{size} byte")
        if digest.hexdigest().lower() != sha256.lower():
            raise LocalAIError("checksum", "SHA256 không khớp")
        os.replace(part, dest)
    except LocalAIError:
        part.unlink(missing_ok=True)
        raise
    except OSError as exc:
        part.unlink(missing_ok=True)
        raise LocalAIError("network", str(exc)) from exc


def pick_engine_asset(releases: Any, cpu: str, system: str = "win32") -> tuple[str, str, int, str]:
    """``(tên, url, kích thước, sha256)`` của gói chạy khớp hệ điều hành + kiến trúc, lấy từ bản mới nhất CÓ gói đó trong danh
    sách release của GitHub (mới trước; vài bản không kèm gói chạy hoặc đang tải lên dở thì bỏ qua).

    Windows: ``llama-bNNNN-bin-win-cpu-<cpu>.zip``. macOS: ``llama-bNNNN-bin-macos-<cpu>.tar.gz`` (có Metal, chạy GPU của chip Apple).

    Raises:
        LocalAIError: ``notfound`` (không bản nào có gói hợp lệ kèm ``digest`` SHA256).
    """
    kind = f"macos-{cpu}" if system == "darwin" else f"win-cpu-{cpu}"
    pattern = re.compile(rf"^llama-.+-bin-{re.escape(kind)}\.(zip|tar\.gz)$")
    assets = [asset for release in (releases if isinstance(releases, list) else [])
              if isinstance(release, dict) and not release.get("draft") for asset in release.get("assets", [])]
    for asset in assets:
        name = str(asset.get("name", ""))
        digest = str(asset.get("digest") or "")
        if pattern.match(name) and digest.startswith("sha256:") and isinstance(asset.get("size"), int):
            return name, str(asset["browser_download_url"]), int(asset["size"]), digest.split(":", 1)[1]
    raise LocalAIError("notfound", f"không có gói {kind} kèm SHA256")


def safe_extract(archive: Path, dest: Path) -> None:
    """Giải nén ``.zip`` hoặc ``.tar.gz``, từ chối mục đi ra ngoài ``dest`` (zip slip, liên kết trỏ ra ngoài, đường dẫn tuyệt đối)."""
    if archive.name.endswith(".tar.gz"):
        try:
            with tarfile.open(archive, "r:gz") as tf:
                tf.extractall(dest, filter="data")     # bộ lọc "data": chặn đường dẫn/symlink ra ngoài, bỏ setuid, thiết bị
        except (tarfile.TarError, OSError) as exc:
            raise LocalAIError("checksum", f"gói không hợp lệ: {exc}") from exc
        return
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest / member.filename).resolve()
            if root != target and root not in target.parents:
                raise LocalAIError("checksum", f"đường dẫn lạ trong gói: {member.filename}")
        zf.extractall(dest)


def install_engine(progress: Progress, cancel: threading.Event) -> None:
    """Tải gói ``llama.cpp`` chính thức mới nhất (đúng hệ điều hành + kiến trúc), kiểm SHA256, giải nén vào ``bin``."""
    if not SUPPORTED:
        raise LocalAIError("unsupported")
    name, url, size, sha = pick_engine_asset(_fetch_json(ENGINE_RELEASE_API), arch(), sys.platform)
    root = _root()
    archive = root / name
    download_file(url, archive, size, sha, progress, cancel)
    staging = root / "bin.new"
    shutil.rmtree(staging, ignore_errors=True)
    try:
        safe_extract(archive, staging)
        exe = next(staging.rglob(_EXE), None)
        if exe is None or not exe.is_file():
            raise LocalAIError("notfound", f"gói không có {_EXE}")
        if not _WIN:
            exe.chmod(0o755)                             # chắc chắn chạy được (tar giữ quyền, phòng gói lạ)
        SERVER.stop()
        shutil.rmtree(bin_dir(), ignore_errors=True)
        os.replace(exe.parent, bin_dir())               # thư mục chứa exe + các DLL/dylib đi kèm
        (bin_dir() / "SOURCE.txt").write_text(f"{name}\n{sha}\n", "utf-8")
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        archive.unlink(missing_ok=True)


def model_meta(model: LocalModel) -> tuple[int, str]:
    """``(kích thước, sha256)`` của file model, đọc từ API cây thư mục của Hugging Face (trường ``lfs``)."""
    for entry in _fetch_json(HF_TREE_API.format(repo=model.repo)):
        if isinstance(entry, dict) and entry.get("path") == model.file:
            lfs = entry.get("lfs") or {}
            if isinstance(lfs.get("size"), int) and re.fullmatch(r"[0-9a-f]{64}", str(lfs.get("oid", ""))):
                return int(lfs["size"]), str(lfs["oid"])
    raise LocalAIError("notfound", f"{model.repo}/{model.file}")


def download_model(model: LocalModel, progress: Progress, cancel: threading.Event) -> None:
    size, sha = model_meta(model)
    download_file(HF_FILE.format(repo=model.repo, file=model.file), model_path(model), size, sha, progress, cancel)


class Downloader:
    """Một lượt tải tại một thời điểm (engine nếu thiếu, rồi model) trên luồng nền; giao diện hỏi ``status`` để vẽ tiến trình."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._state: dict[str, Any] = {"active": False, "model": "", "phase": "", "done": 0, "total": 0, "error": ""}

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _set(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    def start(self, model_id: str) -> bool:
        """Bắt đầu tải ``model_id``; ``False`` nếu đang tải dở hoặc mã model lạ."""
        model = find(model_id)
        with self._lock:
            if model is None or self._state["active"]:
                return False
            self._cancel = threading.Event()
            self._state = {"active": True, "model": model_id, "phase": "engine" if not engine_ready() else "model",
                           "done": 0, "total": 0, "error": ""}
        threading.Thread(target=self._run, args=(model, self._cancel), name="chotto-local-ai-dl", daemon=True).start()
        return True

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self, model: LocalModel, cancel: threading.Event) -> None:
        def progress(done: int, total: int) -> None:
            self._set(done=done, total=total)

        try:
            if not engine_ready():
                self._set(phase="engine", done=0, total=0)
                install_engine(progress, cancel)
            if not model_path(model).is_file():
                self._set(phase="model", done=0, total=0)
                download_model(model, progress, cancel)
            self._set(active=False, phase="done")
        except LocalAIError as exc:
            _LOG.warning("Tải AI Local thất bại: %s", exc)
            self._set(active=False, error=exc.code)
        except Exception:  # noqa: BLE001 - luồng nền không được chết im lặng, giao diện phải thấy lỗi
            _LOG.exception("Tải AI Local lỗi")
            self._set(active=False, error="network")


DOWNLOADS: Final[Downloader] = Downloader()


# ---- server ----
def _record_path() -> Path:
    return _root() / "server.json"


def _read_record() -> dict[str, Any]:
    try:
        data = json.loads(_record_path().read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _mac_exe_path(pid: int) -> str | None:
    """Đường dẫn file chạy của tiến trình ``pid`` (macOS, ``proc_pidpath`` của libproc); ``None`` nếu không đọc được."""
    import ctypes

    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib")
        buffer = ctypes.create_string_buffer(4096)          # PROC_PIDPATHINFO_MAXSIZE
        size = int(libproc.proc_pidpath(ctypes.c_int(pid), buffer, ctypes.c_uint32(len(buffer))))
    except (OSError, AttributeError):
        return None
    return buffer.value.decode("utf-8", "surrogateescape") if size > 0 else None


def _pid_is_llama(pid: int) -> bool:
    """PID còn sống và đúng là ``llama-server`` (phòng PID cũ đã được hệ điều hành cấp cho tiến trình khác)."""
    if not SUPPORTED or pid <= 0:
        return False
    if _MAC:
        path = _mac_exe_path(pid)
        if path is None:
            return False
        # Đường dẫn file chạy thật (proc_pidpath, không phải argv[0] như "ps -o comm"): chỉ tắt đúng server của CHOTTO.
        try:
            return Path(path).resolve() == server_exe().resolve()
        except OSError:
            return False
    try:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             timeout=5, creationflags=_CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return f'"{_EXE}"'.lower() in out.lower()


def _kill_recorded(model_id: str | None = None) -> None:
    """Tắt server ghi trong ``server.json`` (của tiến trình khác hoặc còn sót lại); ``model_id``: chỉ khi đang chạy model đó."""
    record = _read_record()
    if model_id is not None and record.get("model") != model_id:
        return
    pid = record.get("pid")
    if isinstance(pid, int) and _pid_is_llama(pid):
        try:
            os.kill(pid, signal.SIGTERM)                    # Windows: TerminateProcess
        except OSError:
            _LOG.debug("Không tắt được llama-server %s", pid, exc_info=True)
    _record_path().unlink(missing_ok=True)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class LocalServer:
    """``llama-server.exe`` của agent: chạy khi cần, dùng lại nếu cùng model, tự tắt khi rảnh."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._model = ""
        self._port = 0
        self._last = 0.0
        self._watcher: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure(self, model: LocalModel, wait_s: float = 120.0) -> str:
        """URL gốc (``http://127.0.0.1:<cổng>``) của server đang chạy ``model``; khởi chạy và đợi ``/health`` nếu cần.

        Raises:
            LocalAIError: ``unsupported`` | ``notfound`` (thiếu engine/model) | ``start`` (không lên được).
        """
        with self._lock:
            self._last = time.monotonic()
            if self.running and self._model == model.id:
                return f"http://127.0.0.1:{self._port}"
            self._stop_locked()
            if not SUPPORTED:
                raise LocalAIError("unsupported")
            if not engine_ready() or not model_path(model).is_file():
                raise LocalAIError("notfound")
            _kill_recorded()                                     # server mồ côi của lần chạy trước
            port = _free_port()
            log = open(_root() / "server.log", "wb")             # noqa: SIM115 - tiến trình con giữ file tới khi thoát
            try:
                self._proc = subprocess.Popen(
                    [str(server_exe()), "-m", str(model_path(model)), "--host", "127.0.0.1", "--port", str(port),
                     "-c", "4096", "-np", "1"],   # 1 luồng hỏi: bản mới tự chia ngữ cảnh cho nhiều luồng, lời nhắc tiếng Việt sẽ không vừa
                    cwd=str(bin_dir()), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=_NO_WINDOW)
            except OSError as exc:
                raise LocalAIError("start", str(exc)) from exc
            finally:
                log.close()
            self._model, self._port = model.id, port
            _record_path().write_text(json.dumps({"pid": self._proc.pid, "model": model.id, "port": port}), "utf-8")
            self._start_watcher()
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    self._stop_locked()
                    raise LocalAIError("start", "llama-server thoát khi nạp model (xem local_ai/server.log)")
                try:
                    with urllib.request.urlopen(base + "/health", timeout=2) as response:  # noqa: S310 - máy này
                        if response.status == 200:
                            self._last = time.monotonic()
                            return base
                except (OSError, urllib.error.HTTPError):
                    pass                                         # 503 trong lúc nạp model
                time.sleep(0.25)
            self._stop_locked()
            raise LocalAIError("start", "quá thời gian chờ nạp model")

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def stop_unless(self, keep: Callable[[str], bool]) -> None:
        """Tắt server trừ khi ``keep(model đang chạy)``; ``keep`` được gọi TRONG khóa (đọc cấu hình mới nhất, không dùng
        bản đọc trước khi chờ khóa: người dùng có thể vừa chọn lại đúng model đang nạp)."""
        with self._lock:
            if self._proc is not None and not keep(self._model):
                self._stop_locked()

    def stop_if_model(self, model_id: str) -> None:
        with self._lock:
            if self._model == model_id:
                self._stop_locked()

    def _stop_locked(self) -> None:
        proc, self._proc, self._model = self._proc, None, ""
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        if _read_record().get("pid") == proc.pid:
            _record_path().unlink(missing_ok=True)

    def _start_watcher(self) -> None:
        if self._watcher is not None and self._watcher.is_alive():
            return

        def watch() -> None:
            while True:
                time.sleep(15)
                with self._lock:
                    if self._proc is None:
                        self._watcher = None
                        return
                    if time.monotonic() - self._last > IDLE_S:
                        _LOG.info("AI Local rảnh %d giây: tắt llama-server", int(IDLE_S))
                        self._stop_locked()
                        self._watcher = None
                        return

        self._watcher = threading.Thread(target=watch, name="chotto-local-ai-idle", daemon=True)
        self._watcher.start()


SERVER: Final[LocalServer] = LocalServer()
atexit.register(SERVER.stop)                      # agent thoát bằng đường nào cũng không để llama-server mồ côi giữ RAM


def _retry(action: Callable[[], None]) -> None:
    """Tiến trình vừa bị tắt có thể còn giữ file vài trăm mili-giây: thử lại tới ~3 giây."""
    for attempt in range(10):
        try:
            action()
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.3)


def delete_model(model_id: str) -> bool:
    """Xóa file model (tắt server đang dùng nó trước, kể cả server của agent ở tiến trình khác). ``False`` nếu mã lạ.

    Xóa xong mà không còn model nào (và không đang tải) thì dọn SẠCH cả thư mục ``local_ai``: engine, log, file tạm.
    """
    model = find(model_id)
    if model is None:
        return False
    SERVER.stop_if_model(model_id)
    _kill_recorded(model_id)
    path = model_path(model)
    _retry(lambda: path.unlink(missing_ok=True))
    path.with_name(path.name + ".part").unlink(missing_ok=True)
    if not any(model_path(m).is_file() for m in CATALOG) and not DOWNLOADS.status()["active"]:
        SERVER.stop()
        _kill_recorded()
        root = _root()

        def wipe() -> None:
            if root.exists():
                shutil.rmtree(root)

        _retry(wipe)
    return True


def status() -> dict[str, Any]:
    """Dữ liệu cho giao diện: danh mục kèm trạng thái đã tải, engine có chưa, tiến trình tải."""
    return {
        "supported": SUPPORTED,
        "engine_ready": engine_ready(),
        "models": [{"id": m.id, "name": m.name, "short": m.short, "format": m.format, "quant": m.quant,
                    "size_gb": m.size_gb, "ram_gb": m.ram_gb, "downloaded": model_path(m).is_file()} for m in CATALOG],
        "download": DOWNLOADS.status(),
    }
