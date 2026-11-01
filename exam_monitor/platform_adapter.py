# -*- coding: utf-8 -*-
"""平台抽象层：统一 Windows / Linux(X11) / macOS 下的
前台窗口检测、进程枚举、强制关闭进程、浏览器标签页读取。

优先使用 Windows（真实考试环境）；Linux X11 下通过 wmctrl/xprop 提供
等价能力，便于开发与测试；其他平台降级为仅按进程名监控。
"""

import os
import platform
import re
import shutil
import subprocess
import sys
import time

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_X11 = (not IS_WIN) and (not IS_MAC) and \
    bool(os.environ.get("DISPLAY")) and shutil.which("wmctrl")


def _run(cmd, timeout=5):
    """运行外部命令，返回 stdout（失败返回空串）。"""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return p.stdout or ""
    except Exception:
        return ""


# --------------------------------------------------------------------------
# 前台窗口 & 窗口标题
# --------------------------------------------------------------------------

def get_foreground_window():
    """返回 (pid, window_title)，取不到时返回 (None, "")。"""
    if IS_WIN:
        return _win_foreground()
    if IS_X11:
        return _x11_active_window()
    return None, ""


def list_visible_windows():
    """返回 [(pid, title), ...] 所有可见窗口（用于兜底检测）。"""
    if IS_WIN:
        return _win_list_windows()
    if IS_X11:
        return _x11_list_windows()
    return []


# ---------------- Windows ----------------

_win_user32 = None
_win_kernel32 = None


def _init_win():
    global _win_user32, _win_kernel32
    if _win_user32 is None:
        import ctypes
        import ctypes.wintypes
        _win_user32 = ctypes.windll.user32
        _win_kernel32 = ctypes.windll.kernel32
    return _win_user32, _win_kernel32


def _win_foreground():
    try:
        import ctypes
        user32, kernel32 = _init_win()
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, ""
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        pidref = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pidref))
        return int(pidref.value), title
    except Exception:
        return None, ""


def _win_list_windows():
    import ctypes
    try:
        user32, _ = _init_win()
        result = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool, ctypes.c_void_p, ctypes.c_long)

        def cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    pidref = ctypes.c_ulong(0)
                    user32.GetWindowThreadProcessId(
                        hwnd, ctypes.byref(pidref))
                    result.append((int(pidref.value), buf.value))
            return True

        user32.EnumWindows(EnumWindowsProc(cb), 0)
        return result
    except Exception:
        return []


# ---------------- Linux X11 ----------------

def _x11_pid_of_winid(winid):
    out = _run(["xprop", "-id", winid, "_NET_WM_PID"])
    m = re.search(r"=\s*(\d+)", out)
    return int(m.group(1)) if m else None


def _x11_active_window():
    out = _run(["wmctrl", "-a"])
    lines = [l for l in out.splitlines() if l.strip()]
    if len(lines) < 2:
        return None, ""
    # 格式: 桌面 窗口id 主机 标题
    parts = lines[1].split(None, 3)
    if len(parts) < 4:
        return None, ""
    pid = _x11_pid_of_winid(parts[1])
    return pid, parts[3]


def _x11_list_windows():
    out = _run(["wmctrl", "-lp"])
    wins = []
    for line in out.splitlines()[1:]:
        parts = line.split(None, 4)
        if len(parts) >= 5:
            try:
                pid = int(parts[2])
            except ValueError:
                continue
            if pid > 0:
                wins.append((pid, parts[4]))
    return wins


# --------------------------------------------------------------------------
# 进程枚举 / 强制关闭
# --------------------------------------------------------------------------

def _iter_processes_psutil():
    import psutil
    for p in psutil.process_iter(["pid", "name"]):
        try:
            yield p.info["pid"], (p.info["name"] or "").lower()
        except Exception:
            continue


def _proc_name_win32(pid):
    """用 ctypes PSAPI QueryFullProcessImageNameW 取进程名。"""
    import ctypes
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        if ctypes.windll.kernel32.QueryFullProcessImageNameW(
                h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return None
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def _iter_processes_win32():
    import ctypes
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_uint32),
            ("cntUsage", ctypes.c_uint32),
            ("th32ProcessID", ctypes.c_uint32),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", ctypes.c_uint32),
            ("cntThreads", ctypes.c_uint32),
            ("th32ParentProcessID", ctypes.c_uint32),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_uint32),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    snap = ctypes.windll.kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPPROCESS, 0)
    if snap == -1 or snap == 0xFFFFFFFFFFFFFFFF:
        return
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = ctypes.windll.kernel32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            yield int(pe.th32ProcessID), pe.szExeFile.lower()
            ok = ctypes.windll.kernel32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        ctypes.windll.kernel32.CloseHandle(snap)


def _iter_processes_posix():
    """读 /proc（Linux）；macOS 或无 /proc 时用 ps 命令兜底。"""
    if os.path.isdir("/proc"):
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            name = None
            try:
                with open("/proc/%d/comm" % pid, "r") as f:
                    name = f.read().strip()
            except Exception:
                pass
            if not name:
                try:
                    exe = os.readlink("/proc/%d/exe" % pid)
                    name = os.path.basename(exe)
                except Exception:
                    continue
            yield pid, name.lower()
        return
    try:
        out = subprocess.run(["ps", "-axo", "pid=,comm="],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            yield int(parts[0]), \
                os.path.basename(parts[1].strip()).lower()


def iter_processes():
    """生成 (pid, name)。优先 psutil，缺失时自动降级为系统原生方式。"""
    try:
        import psutil  # noqa: F401
    except ImportError:
        pass
    else:
        yield from _iter_processes_psutil()
        return
    if IS_WIN:
        yield from _iter_processes_win32()
    else:
        yield from _iter_processes_posix()


def kill_process(pid, grace=1.0):
    """强制结束进程，返回 True/False。"""
    try:
        import psutil
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(timeout=grace)
        except psutil.TimeoutExpired:
            p.kill()
        return True
    except ImportError:
        return _kill_process_native(pid, grace)
    except Exception:
        return False


def _kill_process_native(pid, grace):
    import signal
    try:
        if IS_WIN:
            import ctypes
            PROCESS_TERMINATE = 0x0001
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_TERMINATE, False, pid)
            if not h:
                return False
            ok = bool(ctypes.windll.kernel32.TerminateProcess(h, 0))
            ctypes.windll.kernel32.CloseHandle(h)
            return ok
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + grace
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                return True
            time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# 浏览器标签页 URL 读取（尽力而为）
# --------------------------------------------------------------------------

CHROME_FAMILY = ("chrome", "msedge", "edge", "chromium", "opera", "brave")

# 监控的浏览器集合（Chromium 系 + Firefox）
SUPPORTED_BROWSERS = CHROME_FAMILY + ("firefox",)


def _find_profile_dirs(exe_base):
    """在常见用户数据目录中查找浏览器 profile（含 Default / Profile 1 ...）。"""
    home = os.path.expanduser("~")
    root = None
    if IS_WIN:
        appdata = os.environ.get("LOCALAPPDATA", "")
        local = os.environ.get("LOCALAPPDATA", "")
        roaming = os.environ.get("APPDATA", "")
        mapping = {
            "chrome":   os.path.join(local, "Google", "Chrome", "User Data"),
            "msedge":   os.path.join(local, "Microsoft", "Edge",
                                     "User Data"),
            "edge":     os.path.join(local, "Microsoft", "Edge",
                                     "User Data"),
            "chromium": os.path.join(local, "Chromium", "User Data"),
            "opera":    os.path.join(local, "Opera Software",
                                     "Opera Stable"),
            "brave":    os.path.join(local, "BraveSoftware",
                                     "Brave-Browser", "User Data"),
            # Firefox：Local 目录存放 sessionstore*
            "firefox":  os.path.join(local, "Firefox", "Profiles"),
        }
        if exe_base == "firefox" and not os.path.isdir(
                mapping["firefox"] or ""):
            # 某些安装会把 Profiles 放在 Roaming 下
            mapping["firefox"] = os.path.join(roaming, "Mozilla", "Firefox",
                                              "Profiles")
        root = mapping.get(exe_base)
    elif IS_MAC:
        base = os.path.join(home, "Library", "Application Support")
        mapping = {
            "chrome":   os.path.join(base, "Google", "Chrome"),
            "msedge":   os.path.join(base, "Microsoft Edge"),
            "edge":     os.path.join(base, "Microsoft Edge"),
            "chromium": os.path.join(base, "Chromium"),
            "opera":    os.path.join(base, "com.operasoftware.Opera"),
            "brave":    os.path.join(base, "BraveSoftware",
                                     "Brave-Browser"),
            "firefox":  os.path.join(base, "Firefox", "Profiles"),
        }
        root = mapping.get(exe_base)
    else:
        mapping = {
            "chrome":   ".config/google-chrome",
            "msedge":   ".config/microsoft-edge",
            "edge":     ".config/microsoft-edge",
            "chromium": ".config/chromium",
            "opera":    ".config/opera",
            "brave":    ".config/BraveSoftware/Brave-Browser",
            "firefox":  ".mozilla/firefox",
        }
        rel = mapping.get(exe_base)
        if rel:
            root = os.path.join(home, rel)
    if not root or not os.path.isdir(root):
        return []
    found = []
    if exe_base == "firefox":
        # profiles.ini 指向的目录优先，其次扫描 *.default* 目录
        try:
            import configparser
            ini = os.path.join(root, "profiles.ini")
            if os.path.exists(ini):
                cp = configparser.ConfigParser()
                cp.read(ini, encoding="utf-8")
                for sec in cp.sections():
                    rp = cp[sec].get("Path")
                    if rp:
                        pd = os.path.normpath(os.path.join(root, rp))
                        if os.path.isdir(pd):
                            found.append(pd)
        except Exception:
            pass
        # <Profiles>/<随机>.default(-release)/
        for d in sorted(os.listdir(root)):
            pd = os.path.join(root, d)
            if os.path.isdir(pd) and (d.endswith(".default")
                                      or ".default" in d):
                if pd not in found:
                    found.append(pd)
    else:
        # User Data/<Default|Profile 1|...>，Opera 等直接就是根目录
        for d in sorted(os.listdir(root)):
            pd = os.path.join(root, d)
            if os.path.isdir(pd) and (d == "Default"
                                      or d.startswith("Profile ")):
                found.append(pd)
        if not found and os.path.isdir(os.path.join(root, "Sessions")):
            found.append(root)
    return found


def _read_session_urls(profile_dir):
    """从浏览器 Session_* 文件解析出当前打开的 URL（尽力而为）。"""
    urls = []
    sess_files = []
    for d in (profile_dir, os.path.join(profile_dir, "Sessions")):
        if os.path.isdir(d):
            for fn in os.listdir(d):
                if fn.startswith(("Session_", "Tabs_")):
                    sess_files.append(os.path.join(d, fn))
    for sf in sess_files:
        try:
            with open(sf, "rb") as f:
                data = f.read()
        except OSError:
            continue
        # session 文件为二进制快照，但 URL 以可打印字符串形式存在
        for m in re.finditer(rb"https?://[^\x00\x01-\x1f\"'<> ]{4,}", data):
            try:
                u = m.group(0).decode("utf-8", "ignore")
            except Exception:
                continue
            urls.append(u)
    return urls


def _read_sessionstore_urls(pd):
    """解析 Firefox profile 的 sessionstore*，返回当前打开标签页 URL。

    支持三种格式：
      1. sessionstore.jsonlz4 —— Mozilla LZ4 帧格式（'LZ4' 魔数 + 8 字节头，
         之后为 lz4.block，首 4 字节小端存原始长度）；
      2. recovery/junrecovery/sessionstore.js —— 旧版明文 JSON；
      3. backup/*.jsonlz4 —— 上一次会话备份（兜底）。
    优先按 windows[].tabs[].entries[] 结构化提取当前 URL（取每个标签最新
    history 条目）；结构解析失败时退回正则全文扫描。
    """
    import json

    def _lz4_block_decompress(src, expected_size=None):
        """纯标准库实现的 LZ4 block 解压器（无 lz4 包时的兜底）。"""
        out = bytearray()
        i = 0
        n = len(src)
        limit = expected_size if expected_size else float("inf")
        while i < n and len(out) < limit:
            token = src[i]
            i += 1
            lit = token >> 4
            if lit == 15:
                while True:
                    b = src[i]
                    i += 1
                    lit += b
                    if b != 255:
                        break
            out += src[i:i + lit]
            i += lit
            if i >= n:
                break  # 以 literal 结尾的块
            off = int.from_bytes(src[i:i + 2], "little")
            i += 2
            if off == 0:
                raise ValueError("bad lz4 offset")
            length = token & 0x0F
            if length == 15:
                while True:
                    b = src[i]
                    i += 1
                    length += b
                    if b != 255:
                        break
            length += 4
            start = len(out) - off
            if start < 0:
                raise ValueError("lz4 match out of range")
            for k in range(length):
                out.append(out[start + k])
        return bytes(out[:limit] if limit != float("inf") else out)

    def _decompress_jsonlz4(path):
        """Mozilla LZ4 帧格式：'LZ4'+描述符(1)+保留(4)=8 字节头，
        之后是 lz4.block 数据（首 4 字节小端为原始长度）。"""
        with open(path, "rb") as f:
            data = f.read()
        if not data.startswith(b"LZ4"):
            return None
        body = data[8:]
        raw_len = int.from_bytes(body[:4], "little") \
            if len(body) >= 4 else None
        # 1) 优先用 python-lz4（快）
        try:
            import lz4.block
            try:
                dec = lz4.block.decompress(body)
            except Exception:
                dec = lz4.block.decompress(body[4:],
                                           uncompressed_size=raw_len or
                                           64 * 1024 * 1024)
            return json.loads(dec.decode("utf-8", "replace"))
        except ImportError:
            pass
        except Exception:
            return None
        # 2) 零依赖：内置纯 Python LZ4 block 解码
        try:
            dec = _lz4_block_decompress(body[4:], raw_len)
            return json.loads(dec.decode("utf-8", "replace"))
        except Exception:
            try:
                dec = _lz4_block_decompress(body)
                return json.loads(dec.decode("utf-8", "replace"))
            except Exception:
                return None

    def _urls_from_obj(obj):
        urls = []
        try:
            for win in obj.get("windows", []) or []:
                for tab in win.get("tabs", []) or []:
                    entries = tab.get("entries", []) or []
                    if not entries:
                        continue
                    # last entry = 当前正在显示的页面
                    for e in entries[-1:]:
                        u = e.get("url", "")
                        if u.startswith(("http://", "https://")):
                            urls.append(u)
                # 其它历史条目也收集，便于事后核查（导航过哪里）
                for tab in win.get("tabs", []) or []:
                    for e in tab.get("entries", []) or [][:-1]:
                        u = e.get("url", "")
                        if u.startswith(("http://", "https://")):
                            urls.append(u)
        except Exception:
            return None
        return urls

    candidates = []
    for fn in ("sessionstore.jsonlz4", "sessionstore.js",
               "sessionstore-backups/recovery.jsonlz4",
               "sessionstore-backups/recovery.json",
               "sessionstore-backups/junrecovery.jsonlz4",
               "sessionstore-backups/upgrade.jsonlz4"):
        p = os.path.join(pd, fn)
        if os.path.exists(p):
            candidates.append(p)
    urls = []
    for p in candidates:
        got = None
        if p.endswith(".jsonlz4"):
            obj = _decompress_jsonlz4(p)
            if obj is not None:
                got = _urls_from_obj(obj)
                if got is None:
                    got = _regex_urls_in_text(open(p, "rb").read())
        else:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    obj = json.load(f)
                got = _urls_from_obj(obj)
            except Exception:
                got = _regex_urls_in_text(open(p, "rb").read())
        if got:
            urls.extend(got)
    return urls


_URL_RE_BYTES = re.compile(
    b"https?://[^" + bytes(range(0x21)) + b"\"'<>\\\\\x7f]{4,}")


def _regex_urls_in_text(data_bytes):
    out = []
    for m in _URL_RE_BYTES.finditer(data_bytes):
        try:
            out.append(m.group(0).decode("utf-8", "ignore"))
        except Exception:
            continue
    return out


def get_browser_open_urls():
    """返回 {浏览器名: {"current": [...], "history": [...]}} ，读不到则空 dict。

    current 为尽力判断的"当前显示页面"（Chromium 系取自 Session/Tabs 快照中
    最后写入的条目及前台窗口标题；Firefox 取自 sessionstore 每个标签的最新
    history 条目）；history 为快照里出现过的全部 URL，供事后核查。
    """
    result = {}
    running = set()
    for pid, name in iter_processes():
        base = name.replace(".exe", "")
        if base == "edge":
            base = "msedge"
        if base in SUPPORTED_BROWSERS:
            running.add(base)
    if not running:
        return result

    # Chromium 系：Session/Tabs 快照
    for base in sorted(running):
        if base == "firefox":
            continue
        urls = []
        for prof in _find_profile_dirs(base):
            urls.extend(_read_session_urls(prof))
        if urls:
            disp = _display_name(base)
            result[disp] = {"current": _guess_current(urls),
                            "history": sorted(set(urls))}

    # Firefox：sessionstore.jsonlz4（结构化解析，含正则兜底）
    if "firefox" in running:
        urls = []
        for pd in _find_profile_dirs("firefox"):
            urls.extend(_read_sessionstore_urls(pd))
        if urls:
            result["Firefox"] = {"current": _guess_current(urls),
                                 "history": sorted(set(urls))}

    # 兜底增强：从可见窗口标题中提取 URL（Chrome/Edge/Firefox 均适用）
    titles = []
    try:
        for _, t in list_visible_windows():
            if t:
                titles.append(t)
    except Exception:
        pass
    for t in titles:
        for u in _regex_urls_in_text(t.encode("utf-8", "ignore")):
            disp = _browser_of_title(t)
            if disp:
                ent = result.setdefault(disp, {"current": [], "history": []})
                if u not in ent["current"]:
                    ent["current"].append(u)
    return result


_BROWSER_DISPLAY = {
    "chrome": "Chrome", "msedge": "Microsoft Edge", "chromium": "Chromium",
    "opera": "Opera", "brave": "Brave", "firefox": "Firefox",
}


def _display_name(base):
    return _BROWSER_DISPLAY.get(base, base)


def _browser_of_title(title):
    tl = title.lower()
    if "mozilla firefox" in tl or " - firefox" in tl:
        return "Firefox"
    if "microsoft edge" in tl or " - edge" in tl or "inprivate - microsoft" \
            in tl:
        return "Microsoft Edge"
    if "google chrome" in tl or " - google chrome" in tl:
        return "Chrome"
    if " - chromium" in tl or "chromium" in tl:
        return "Chromium"
    if "- opera" in tl:
        return "Opera"
    if "- brave" in tl:
        return "Brave"
    return None


def _guess_current(urls):
    """快照文件里无法精确区分当前页，把 hydro.ac 相关 URL 视为当前重点，
    其余全部保留在 history 中由 UrlMonitor 一并核查。"""
    return sorted(set(urls))


# --------------------------------------------------------------------------
# 默认浏览器
# --------------------------------------------------------------------------

def launch_default_browser(url):
    """用系统默认浏览器打开 url，返回 Popen 对象或 None。"""
    import webbrowser
    try:
        return webbrowser.open(url, new_window=True)
    except Exception:
        return None
