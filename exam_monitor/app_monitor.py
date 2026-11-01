# -*- coding: utf-8 -*-
"""软件（进程/窗口）监控模块。

规则：除 IDEA / Dev-C++ / Visual C++ / 画图 / 浏览器 之外，
检测到其它软件打开即记录违规，并交由 UI 提示用户是否关闭；
用户选择关闭或超时未处理时强制结束该进程。
"""

import threading
import time

from . import config, platform_adapter


SYSTEM_DISPLAYS = {
    "Windows 资源管理器(系统)", "系统进程", "系统服务", "桌面窗口管理器",
    "系统搜索", "输入法", "输入体验", "任务管理器",
}


def classify_process(name):
    """根据进程名分类。

    返回 (category, display_name)
      category: allowed | browser | system | unknown
    """
    n = name.lower().replace(".exe", "")
    if n in config.IGNORED_PROCESSES:
        return "system", name
    # 1) 精确匹配（避免 git -> g++、node -> code 之类的子串误判）
    for key, disp in config.ALLOWED_PROCESSES.items():
        if n == key:
            if disp in ("Chrome", "Firefox", "Microsoft Edge", "Opera",
                        "Brave", "Safari"):
                return "browser", disp
            if disp in SYSTEM_DISPLAYS:
                return "system", disp
            return "allowed", disp
    # 2) 前缀/包含匹配，但要求关键字足够长（>=4），减少误报
    for key, disp in config.ALLOWED_PROCESSES.items():
        if len(key) >= 4 and (key in n or n.startswith(key)):
            if disp in ("Chrome", "Firefox", "Microsoft Edge", "Opera",
                        "Brave", "Safari"):
                return "browser", disp
            if disp in SYSTEM_DISPLAYS:
                return "system", disp
            return "allowed", disp
    # 3) 短关键字单独处理：cl.exe / gcc / g++ / wt 等只允许完全相等或带扩展名
    if n in ("cl", "gcc", "g++", "wt", "code"):
        return "allowed", config.ALLOWED_PROCESSES.get(n, n)
    # 常见误报兜底：包含浏览器关键字
    if "chrome" in n or "firefox" in n or "edge" in n:
        return "browser", name
    if n.startswith(("svchost", "system", "win-", "csrss", "services")):
        return "system", name
    return "unknown", name


class AppMonitor(threading.Thread):
    """周期扫描进程与前台窗口，发现非白名单软件 -> on_violation 回调。

    on_violation(info) 需返回 True(已关闭/强制关闭) 或 False(用户拒绝关闭)。
    info = {pid, name, title, first_seen}
    """

    def __init__(self, on_violation, poll=1.0):
        super().__init__(daemon=True)
        self.on_violation = on_violation
        self.poll = poll
        self._stop = threading.Event()
        self._lock = threading.Lock()
        # pid -> info，当前正在被跟踪的可疑进程
        self.suspicious = {}
        # 已经处理过、允许其继续存在的 pid（用户点了"不关闭"）
        self.keep_pids = set()
        # 曾经出现过的进程名基线（考试开始前已在运行的软件不算新开）
        self.baseline_names = set()
        self.enabled = True

    # ------------------------------------------------------------------
    def snapshot_baseline(self):
        for _, name in platform_adapter.iter_processes():
            cat, _ = classify_process(name)
            if cat == "unknown":
                self.baseline_names.add(name)

    def stop(self):
        self._stop.set()

    # ------------------------------------------------------------------
    def run(self):
        while not self._stop.is_set():
            try:
                if self.enabled:
                    self._scan()
            except Exception as e:  # 监控线程绝不能崩
                print("[app_monitor] scan error:", e, flush=True)
            self._stop.wait(self.poll)

    def _scan(self):
        now = time.time()
        alive_pids = set()
        new_found = []

        # 1) 按进程扫描
        for pid, name in platform_adapter.iter_processes():
            alive_pids.add(pid)
            cat, disp = classify_process(name)
            if cat != "unknown":
                continue
            with self._lock:
                if pid in self.suspicious or pid in self.keep_pids:
                    continue
            if name in self.baseline_names:
                # 考前就在运行：加入 keep，避免开局连环弹窗
                with self._lock:
                    self.keep_pids.add(pid)
                continue
            info = {"pid": pid, "name": name, "title": "",
                    "first_seen": now}
            new_found.append(info)

        # 2) 按前台窗口补充标题（Windows/X11 有效）
        fg_pid, fg_title = platform_adapter.get_foreground_window()
        if fg_pid and fg_title:
            for info in new_found:
                if info["pid"] == fg_pid:
                    info["title"] = fg_title

        # 3) 清理已消失的可疑进程记录
        with self._lock:
            gone = [p for p in self.suspicious if p not in alive_pids]
            for p in gone:
                info = self.suspicious.pop(p)
                self._report_close(info, by_user=True)
            self.keep_pids &= alive_pids

        # 4) 上报新违规
        for info in new_found:
            with self._lock:
                self.suspicious[info["pid"]] = info
            handled = False
            try:
                handled = bool(self.on_violation(dict(info)))
            except Exception as e:
                print("[app_monitor] violation cb error:", e, flush=True)
            if handled:
                killed = platform_adapter.kill_process(info["pid"])
                with self._lock:
                    self.suspicious.pop(info["pid"], None)
                self._report_close(info, by_user=False, forced=killed)

    # ------------------------------------------------------------------
    def user_keep(self, pid):
        """用户选择不关闭：记入 keep 名单。"""
        with self._lock:
            self.keep_pids.add(pid)
            self.suspicious.pop(pid, None)

    def _report_close(self, info, by_user, forced=False):
        # 由主程序注入的日志回调（可选）
        cb = getattr(self, "on_closed", None)
        if cb:
            cb(info, by_user, forced)
