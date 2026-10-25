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

def iter_processes():
    """生成 (pid, name) 。"""
    import psutil
    for p in psutil.process_iter(["pid", "name"]):
        try:
            yield p.info["pid"], (p.info["name"] or "").lower()
        except Exception:
            continue


def kill_process(pid, grace=1.0):
    """强制结束进程，返回 True/False。"""
    import psutil
    try:
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(timeout=grace)
        except psutil.TimeoutExpired:
            p.kill()
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# 浏览器标签页 URL 读取（尽力而为）
# --------------------------------------------------------------------------

CHROME_FAMILY = ("chrome", "msedge", "opera", "brave")


def _find_profile_dirs(exe_base):
    """在常见用户数据目录中查找浏览器 profile。"""
    home = os.path.expanduser("~")
    candidates = []
    if IS_WIN:
        appdata = os.environ.get("LOCALAPPDATA", "")
        mapping = {
            "chrome": os.path.join(appdata, "Google", "Chrome", "User Data"),
            "msedge": os.path.join(appdata, "Microsoft",
                                   "Edge", "User Data"),
            "opera":  os.path.join(appdata, "Opera Software",
                                   "Opera Stable"),
            "brave":  os.path.join(appdata, "BraveSoftware",
                                   "Brave-Browser", "User Data"),
        }
        candidates.append(mapping.get(exe_base))
    elif IS_MAC:
        base = os.path.join(home, "Library", "Application Support")
        mapping = {
            "chrome": os.path.join(base, "Google", "Chrome", "Default"),
            "msedge": os.path.join(base, "Microsoft Edge", "Default"),
            "opera":  os.path.join(base, "com.operasoftware.Opera",
                                   "Default"),
            "brave":  os.path.join(base, "BraveSoftware",
                                   "Brave-Browser", "Default"),
        }
        candidates.append(mapping.get(exe_base))
    else:
        mapping = {
            "chrome": ".config/google-chrome/Default",
            "msedge": ".config/microsoft-edge/Default",
            "opera":  ".config/opera/Default",
            "brave":  ".config/BraveSoftware/Brave-Browser/Default",
        }
        rel = mapping.get(exe_base)
        if rel:
            candidates.append(os.path.join(home, rel))
    return [c for c in candidates if c and os.path.isdir(c)]


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


def get_browser_open_urls():
    """返回 {浏览器名: [url,...]} ，读不到则返回空 dict。"""
    result = {}
    seen_names = set()
    for pid, name in iter_processes():
        base = name.replace(".exe", "")
        if base in CHROME_FAMILY and base not in seen_names:
            seen_names.add(base)
            urls = []
            for prof in _find_profile_dirs(base):
                urls.extend(_read_session_urls(prof))
            if urls:
                result[base] = sorted(set(urls))
    # Firefox：走 remote (about:debugging 未开启时不可用) -> 读 places/session
    if "firefox" in seen_names or any(n == "firefox" for _, n in
                                      iter_processes()):
        home = os.path.expanduser("~")
        ff_root = None
        if IS_WIN:
            ff_root = os.path.join(
                os.environ.get("APPDATA", ""), "Mozilla", "Firefox",
                "Profiles")
        elif IS_MAC:
            ff_root = os.path.join(
                home, "Library", "Application Support", "Firefox", "Profiles")
        else:
            ff_root = os.path.join(home, ".mozilla", "firefox", "Profiles")
        if ff_root and os.path.isdir(ff_root):
            for prof in os.listdir(ff_root):
                pd = os.path.join(ff_root, prof)
                jsonf = os.path.join(pd, "sessionstore.jsonlz4")
                legacy = os.path.join(pd, "sessionstore.js")
                target = jsonf if os.path.exists(jsonf) else \
                    (legacy if os.path.exists(legacy) else None)
                if not target:
                    continue
                try:
                    with open(target, "rb") as f:
                        data = f.read()
                    urls = []
                    for m in re.finditer(
                            rb"https?://[^\x00\x01-\x1f\"'<>\\ ]{4,}", data):
                        urls.append(m.group(0).decode("utf-8", "ignore"))
                    if urls:
                        result.setdefault("firefox", []).extend(
                            sorted(set(urls)))
                except OSError:
                    pass
    return result


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
