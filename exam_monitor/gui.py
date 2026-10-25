# -*- coding: utf-8 -*-
"""Tkinter 图形界面：输入域/比赛ID → 开始考试 → 监控面板 → 结束导出报告。

弹窗调度完全在主线程进行（after），保证线程安全。
"""

import getpass
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import config, platform_adapter, report
from .app_monitor import AppMonitor, classify_process
from .events import EventLog, fmt_ts
from .recorder import ScreenRecorder
from .url_monitor import UrlMonitor, is_url_allowed

DOMAIN_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
CID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


class MonitorApp:
    def __init__(self, root):
        self.root = root
        root.title("%s v%s" % (config.APP_NAME, config.VERSION))
        root.geometry("720x560")
        root.minsize(640, 500)

        self.queues = queue.Queue()      # 后台线程 -> UI 的违规请求
        self.log = None
        self.recorder = None
        self.app_mon = None
        self.url_mon = None
        self.contest_url = ""
        self.domain = ""
        self.cid = ""
        self.start_ts = None
        self._pending = None             # 当前正在处理的弹窗请求
        self._browser_proc = None
        self.keep_pids = set()           # 用户选择"不关闭"的进程

        self._build_setup_ui()
        self.root.after(200, self._pump_queue)
        self.root.after(1000, self._tick_clock)

    # ================= 界面：准备页 =================
    def _build_setup_ui(self):
        for w in self.root.winfo_children():
            w.destroy()
        f = ttk.Frame(self.root, padding=20)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="Hydro OJ 在线考试监考",
                  font=("Microsoft YaHei", 16, "bold")).pack(anchor="w")
        ttk.Label(f, foreground="#666", text=(
            "规则：全程录屏；除 IDEA / Dev-C++ / Visual C++ / 画图 / 浏览器 外，\n"
            "禁止打开其它软件（打开将记录并提示关闭）；浏览器只允许访问比赛页面。"
        )).pack(anchor="w", pady=8)

        grid = ttk.Frame(f); grid.pack(fill="x", pady=10)
        ttk.Label(grid, text="域 (domain):").grid(row=0, column=0, sticky="e")
        self.ent_domain = ttk.Entry(grid, width=30)
        self.ent_domain.grid(row=0, column=1, padx=6, pady=4)
        ttk.Label(grid, text="比赛 ID (contest id):").grid(row=1, column=0,
                                                       sticky="e")
        self.ent_cid = ttk.Entry(grid, width=30)
        self.ent_cid.grid(row=1, column=1, padx=6, pady=4)
        self.lbl_preview = ttk.Label(grid, foreground="#1565c0", text="")
        self.lbl_preview.grid(row=2, column=0, columnspan=2, pady=6)
        self.ent_domain.bind("<KeyRelease>", self._update_preview)
        self.ent_cid.bind("<KeyRelease>", self._update_preview)

        row = ttk.Frame(f); row.pack(fill="x", pady=10)
        ttk.Label(row, text="输出目录:").pack(side="left")
        self.ent_out = ttk.Entry(row, width=40)
        self.ent_out.insert(0, os.path.join(os.getcwd(), "exam_records"))
        self.ent_out.pack(side="left", padx=6)
        ttk.Button(row, text="浏览…", command=self._choose_dir).pack(side="left")

        ttk.Button(f, text="🚀 开始考试（启动录屏与监控）",
                   command=self.on_start).pack(pady=16, ipadx=20, ipady=6)

    def _choose_dir(self):
        from tkinter import filedialog
        d = filedialog.askdirectory()
        if d:
            self.ent_out.delete(0, "end"); self.ent_out.insert(0, d)

    def _update_preview(self, *_):
        d, c = self.ent_domain.get().strip(), self.ent_cid.get().strip()
        if d and c:
            self.lbl_preview.config(text="比赛网址: " + config.CONTEST_URL_TEMPLATE
                                    .format(domain=d, cid=c))
        else:
            self.lbl_preview.config(text="")

    # ================= 界面：监控页 =================
    def _build_monitor_ui(self):
        for w in self.root.winfo_children():
            w.destroy()
        top = ttk.Frame(self.root, padding=10); top.pack(fill="x")
        ttk.Label(top, text=self.contest_url, foreground="#1565c0").pack(
            anchor="w")
        self.lbl_status = ttk.Label(top, text="● 录制中", foreground="#c62828",
                                    font=("Microsoft YaHei", 11, "bold"))
        self.lbl_status.pack(anchor="w")
        self.lbl_clock = ttk.Label(top, text="已用时 00:00:00")
        self.lbl_clock.pack(anchor="w")
        self.lbl_counts = ttk.Label(top, text="违规：软件 0 次 / 网址 0 次")
        self.lbl_counts.pack(anchor="w")

        cols = ("time", "kind", "msg", "ack")
        mid = ttk.Frame(self.root); mid.pack(fill="both", expand=True, padx=10)
        self.tree = ttk.Treeview(mid, columns=cols, show="headings")
        for c, t, w in zip(cols, ("时间", "类型", "事件", "处理"),
                           (140, 150, 330, 120)):
            self.tree.heading(c, text=t); self.tree.column(c, width=w)
        sb = ttk.Scrollbar(mid, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("viol", background="#ffe6e6")

        bot = ttk.Frame(self.root, padding=10); bot.pack(fill="x")
        ttk.Button(bot, text="✅ 结束考试并生成报告",
                   command=self.on_end).pack(side="right")
        ttk.Button(bot, text="打开输出目录",
                   command=self._open_outdir).pack(side="left")

    def _open_outdir(self):
        p = self.out_dir
        if not os.path.isdir(p):
            return
        if platform.system() == "Windows":
            os.startfile(p)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", p])
        else:
            subprocess.Popen(["xdg-open", p])

    def _tick_clock(self):
        if self.start_ts:
            s = int(time.time() - self.start_ts)
            self.lbl_clock.config(text="已用时 %02d:%02d:%02d"
                                  % (s // 3600, s % 3600 // 60, s % 60))
        self.root.after(1000, self._tick_clock)

    def _refresh_counts(self):
        vs = self.log.violations()
        n_app = sum(1 for e in vs if e.kind == "app_open")
        n_url = sum(1 for e in vs if e.kind == "url_violation")
        if hasattr(self, "lbl_counts"):
            self.lbl_counts.config(
                text="违规：软件 %d 次 / 网址 %d 次" % (n_app, n_url))

    def _add_row(self, ev):
        if not hasattr(self, "tree"):
            return
        kind_cn = report.KIND_LABEL.get(ev.kind, (ev.kind,))[0]
        ack = report.ACK_LABEL.get(ev.ack, ev.ack or "")
        tags = ("viol",) if ev.kind in ("app_open", "url_violation") else ()
        self.tree.insert("", "end", values=(fmt_ts(ev.ts), kind_cn,
                                            ev.message, ack), tags=tags)
        children = self.tree.get_children()
        if len(children) > 400:
            self.tree.delete(*children[:len(children) - 400])
        self.tree.see(children[-1])

    # ================= 开始 / 结束 =================
    def on_start(self):
        d = self.ent_domain.get().strip()
        c = self.ent_cid.get().strip()
        if not DOMAIN_RE.match(d):
            messagebox.showerror("输入错误", "域只能包含字母/数字/下划线/短横线")
            return
        if not CID_RE.match(c):
            messagebox.showerror("输入错误", "比赛 ID 只能包含字母/数字/下划线/短横线")
            return
        if not messagebox.askyesno(
                "确认开始监考",
                "即将开始监考：\n\n1. 全程录屏\n2. 监控并拦截未授权软件\n"
                "3. 浏览器仅允许访问\n   %s\n\n继续？"
                % config.CONTEST_URL_TEMPLATE.format(domain=d, cid=c)):
            return

        self.domain, self.cid = d, c
        self.contest_url = config.CONTEST_URL_TEMPLATE.format(domain=d, cid=c)
        base_out = self.ent_out.get().strip() or "."
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.out_dir = os.path.join(base_out, "%s_%s" % (c, stamp))
        os.makedirs(self.out_dir, exist_ok=True)

        self.log = EventLog(os.path.join(self.out_dir, config.LOG_FILE))
        self.log.record("session_start", "考试开始：%s" % self.contest_url,
                        {"domain": d, "cid": c})

        # 1) 录屏
        self.recorder = ScreenRecorder(self.out_dir)
        self.recorder.start()
        self.log.record("video", "录屏已启动 (%s)" % self.recorder.method)

        # 2) 软件监控
        self.app_mon = AppMonitor(self._ask_close_dialog, poll=1.0)
        self.app_mon.snapshot_baseline()
        self.app_mon.on_closed = self._on_app_closed
        self.app_mon.start()

        # 3) URL 监控 + 打开默认浏览器
        self.url_mon = UrlMonitor(self.contest_url, d, c,
                                  self._on_url_violation)
        self.url_mon.start()
        self._launch_browser()

        self.start_ts = time.time()
        self._build_monitor_ui()
        for ev in self.log.events:
            self._add_row(ev)

    def _launch_browser(self):
        """优先以 --app 模式启动 Chrome/Edge（无地址栏、窗口受限），
        失败则退回系统默认浏览器。"""
        launched = False
        for exe in ("chrome", "msedge", "google-chrome", "chromium",
                    "chromium-browser"):
            path = shutil_which(exe) or shutil_which(exe + ".exe")
            if not path:
                continue
            try:
                self._browser_proc = subprocess.Popen([
                    path, "--app=%s" % self.contest_url,
                    "--new-window", "--start-maximized",
                    "--disable-session-crashed-bubble",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                launched = True
                self.log.record("browser_launch",
                                "以 --app 模式启动 %s（仅显示比赛页面）" % exe,
                                {"exe": path})
                break
            except OSError:
                continue
        if not launched:
            platform_adapter.launch_default_browser(self.contest_url)
            self.log.record("browser_launch",
                            "已通过系统默认浏览器打开比赛页面")
            self.log.warning("当前浏览器无法自动读取标签页 URL，"
                             "越界访问依赖录屏人工核查（详见 README 限制说明）")

    def on_end(self):
        if not messagebox.askyesno("结束考试", "确认结束考试并生成监考报告？"):
            return
        self.lbl_status.config(text="正在收尾…", foreground="#ef6c00")
        self.root.update_idletasks()
        threading.Thread(target=self._finish, daemon=True).start()

    def _finish(self):
        try:
            self.app_mon.enabled = False
            self.url_mon.enabled = False
            self.app_mon.stop(); self.url_mon.stop()

            video = self.recorder.stop()
            frames_zip = self.recorder.zip_frames()
            duration = time.time() - self.start_ts
            self.log.record("video", "录屏已停止",
                            {"seconds": int(duration)})
            self.log.record("session_end", "考试结束")

            meta = {
                "app": config.APP_NAME,
                "version": config.VERSION,
                "domain": self.domain,
                "cid": self.cid,
                "contest_url": self.contest_url,
                "start_time": fmt_ts(self.start_ts),
                "end_time": fmt_ts(time.time()),
                "duration": duration,
                "user": getpass.getuser(),
                "host": platform.node(),
                "system": "%s %s" % (platform.system(), platform.release()),
                "video": video,
                "frames_zip": frames_zip,
                "record_method": self.recorder.method,
                "video_frames": self.recorder.frame_count,
            }
            jp, hp = report.generate(self.out_dir, self.log, meta)
            self.queues.put(("done", (jp, hp)))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.queues.put(("fatal", str(e)))

    # ================= 弹窗调度（主线程） =================
    def _pump_queue(self):
        if self._pending is None:
            try:
                item = self.queues.get_nowait()
            except queue.Empty:
                item = None
            if item:
                kind, payload = item
                if kind == "app":
                    self._show_app_dialog(payload)
                elif kind == "url":
                    self._show_url_dialog(payload)
                elif kind == "done":
                    self._show_report_done(payload)
                elif kind == "fatal":
                    messagebox.showerror("错误", "生成报告失败: %s" % payload)
                    self.root.destroy(); return
        self.root.after(150, self._pump_queue)

    # ---- 软件违规：提示是否关闭 ----
    def _ask_close_dialog(self, info):
        """工作线程回调：把请求丢给主线程，等待用户决定。
        返回 True => 需要强制关闭该进程。"""
        ev = self.log.violation(
            "app_open",
            "检测到禁用软件打开: %s" % info["name"],
            {"pid": info["pid"], "window": info.get("title", "")})
        self.queues.put(("app", (info, ev)))
        # 超时保护：60 秒无人处理则自动关闭
        deadline = time.time() + 60
        while time.time() < deadline:
            if ev.result is not None:
                break
            time.sleep(0.2)
        if ev.result is None:
            ev.result = "timeout"
        ev.ack = ev.result
        if ev.result == "keep":
            self.app_mon.user_keep(info["pid"])
            self.log.record("info", "用户选择不关闭 %s（已记录在案）"
                            % info["name"], {"pid": info["pid"]},
                            ack="keep")
            return False
        self.log.record("app_forced", "%s 已被关闭" % info["name"],
                        {"pid": info["pid"]}, ack=ev.result)
        return True

    def _show_app_dialog(self, payload):
        info, ev = payload
        self._pending = (info, ev)
        name = info["name"]
        title = info.get("title") or ""
        msg = ("考试期间禁止使用软件「%s」！\n窗口: %s\nPID: %s\n\n"
               "是否立即关闭该软件？\n（选择\"否\"将记录为拒绝关闭，"
               "且 60 秒内不处理将被强制关闭）"
               % (name, title or "(未知)", info["pid"]))
        do_close = messagebox.askyesno("⚠ 监考警告：禁用软件", msg, icon="warning")
        ev.result = "close" if do_close else "keep"
        self._pending = None
        self._add_row(ev)
        self._refresh_counts()

    def _on_app_closed(self, info, by_user, forced):
        if by_user:
            self.log.record("app_close",
                            "禁用软件 %s 已由用户自行关闭" % info["name"],
                            {"pid": info["pid"]})
            self.root.after(0, lambda: self._add_row(
                self.log.events[-1]))

    # ---- URL 违规 ----
    def _on_url_violation(self, url, browser, reason):
        ev = self.log.violation(
            "url_violation",
            "浏览器(%s)访问了非比赛页面: %s" % (browser, url),
            {"reason": reason})
        self.queues.put(("url", (url, browser, reason, ev)))

    def _show_url_dialog(self, payload):
        url, browser, reason, ev = payload
        messagebox.showwarning(
            "⚠ 监考警告：越界访问",
            "检测到浏览器(%s)打开了不在允许范围的页面：\n\n%s\n\n原因: %s\n"
            "只允许访问:\n%s/...\n\n该行为已记录到监考报告。"
            % (browser, url, reason, self.contest_url))
        # 尽力而为：把该浏览器重新导航回比赛页
        self._reclaim_browser(browser)
        self.log.record("url_block", "已将 %s 重置回比赛页面" % browser,
                        ack="auto")
        ev.result = "auto"
        self._add_row(ev)
        self._add_row(self.log.events[-1])
        self._refresh_counts()
        self._pending = None

    def _reclaim_browser(self, browser):
        exe_map = {"chrome": "chrome", "msedge": "msedge",
                   "opera": "opera", "brave": "brave"}
        exe = exe_map.get(browser)
        if exe and shutil_which(exe):
            try:
                subprocess.Popen([shutil_which(exe), self.contest_url],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            except OSError:
                pass
        else:
            platform_adapter.launch_default_browser(self.contest_url)

    # ---- 完成 ----
    def _show_report_done(self, paths):
        jp, hp = paths
        self.lbl_status.config(text="■ 已结束", foreground="#2e7d32")
        ok = messagebox.askyesno(
            "监考结束",
            "报告已生成：\n\n%s\n%s\n\n录屏：%s\n\n是否现在打开 HTML 报告？"
            % (hp, jp, self.recorder.video_path))
        if ok:
            try:
                import webbrowser
                webbrowser.open("file://" + hp.replace(os.sep, "/"))
            except Exception:
                pass


def shutil_which(name):
    import shutil
    return shutil.which(name)


def run():
    root = tk.Tk()
    try:
        root.call("tk", "scaling", 1.2)
    except Exception:
        pass
    MonitorApp(root)
    root.mainloop()


if __name__ == "__main__":
    run()
