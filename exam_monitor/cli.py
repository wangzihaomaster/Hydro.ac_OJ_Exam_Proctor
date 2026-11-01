# -*- coding: utf-8 -*-
"""命令行监考模式（无 GUI 环境可用，也便于自动化测试）。

发现禁用软件：交互模式下提示是否关闭；--auto-close 或 stdin 不可用(EOF)
时直接强制关闭并记录。
"""

import getpass
import os
import platform
import shutil as _sh
import subprocess
import time

from . import config, platform_adapter, report
from .app_monitor import AppMonitor
from .events import EventLog
from .recorder import ScreenRecorder
from .url_monitor import UrlMonitor


def _launch_browser_limited(contest_url, log):
    """CLI 模式：优先用受限方式启动 Chrome/Edge(--app) / Firefox(--kiosk)。"""
    for exe in ("chrome", "msedge", "google-chrome", "chromium",
                "microsoft-edge", "firefox"):
        path = _sh.which(exe) or _sh.which(exe + ".exe")
        if not path:
            continue
        try:
            if exe == "firefox":
                args = [path, "--kiosk", contest_url]
                mode = "--kiosk 全屏锁定"
            else:
                args = [path, "--app=%s" % contest_url, "--new-window"]
                mode = "--app 无地址栏"
            subprocess.Popen(args, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            log.record("browser_launch",
                       "已以 %s 模式启动 %s -> %s" % (mode, exe, contest_url))
            return True
        except OSError:
            continue
    platform_adapter.launch_default_browser(contest_url)
    log.record("browser_launch", "已打开默认浏览器 -> %s" % contest_url)
    return False


def _ask_close(info):
    """终端里询问用户是否关闭。返回 True=关闭。"""
    print("\n" + "=" * 60)
    print("⚠ 监考警告：检测到禁用软件 [%s] (pid=%d)" %
          (info["name"], info["pid"]))
    if info.get("title"):
        print("   窗口标题: %s" % info["title"])
    print("=" * 60)
    try:
        ans = input("是否立即关闭？[Y/n] ").strip().lower()
    except EOFError:
        ans = "y"  # 无人值守 -> 自动关闭
    return ans in ("", "y", "yes")


def cli_main(domain, cid, minutes, out_base, auto_close=False):
    contest_url = config.CONTEST_URL_TEMPLATE.format(domain=domain, cid=cid)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = "%s/%s_%s" % (out_base.rstrip("/"), cid, stamp)
    import os
    os.makedirs(out_dir, exist_ok=True)

    log = EventLog(os.path.join(out_dir, config.LOG_FILE))
    log.record("session_start", "考试开始：%s" % contest_url,
               {"domain": domain, "cid": cid})

    rec = ScreenRecorder(out_dir)
    rec.start()
    log.record("video", "录屏已启动 (%s)" % rec.method)

    def on_violation(info):
        log.violation("app_open",
                      "检测到禁用软件打开: %s" % info["name"],
                      {"pid": info["pid"], "window": info.get("title", "")})
        close = True if auto_close else _ask_close(info)
        if close:
            log.record("app_forced", "%s 被关闭" % info["name"],
                       {"pid": info["pid"]}, ack="close")
            return True
        app_mon.user_keep(info["pid"])
        log.record("info", "用户选择不关闭 %s（已记录在案）" % info["name"],
                   ack="keep")
        return False

    app_mon = AppMonitor(on_violation, poll=1.0)
    app_mon.snapshot_baseline()

    def on_closed(info, by_user, forced):
        if by_user:
            log.record("app_close", "%s 已由用户自行关闭" % info["name"])

    app_mon.on_closed = on_closed
    app_mon.start()

    def on_url_violation(url, browser, reason):
        log.violation("url_violation",
                      "浏览器(%s)访问非比赛页面: %s" % (browser, url),
                      {"reason": reason})
        _launch_browser_limited(contest_url, log)
        log.record("url_block", "已把 %s 重置回比赛页面" % browser, ack="auto")

    url_mon = UrlMonitor(contest_url, domain, cid, on_url_violation)
    url_mon.start()

    _launch_browser_limited(contest_url, log)

    print("\n监考中… %.1f 分钟（Ctrl+C 可提前结束）\n" % minutes)
    t_end = time.time() + minutes * 60
    try:
        while time.time() < t_end:
            time.sleep(1)
    except KeyboardInterrupt:
        log.warning("收到 Ctrl+C，提前结束考试")

    app_mon.enabled = False; url_mon.enabled = False
    app_mon.stop(); url_mon.stop()
    video = rec.stop()
    frames_zip = rec.zip_frames()
    duration = time.time() - log._start_ts
    log.record("video", "录屏已停止", {"seconds": int(duration)})
    log.record("session_end", "考试结束")

    meta = {
        "app": config.APP_NAME, "version": config.VERSION,
        "domain": domain, "cid": cid, "contest_url": contest_url,
        "start_time": log.events[0].to_dict()["time"],
        "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration": duration,
        "user": getpass.getuser(), "host": platform.node(),
        "system": "%s %s" % (platform.system(), platform.release()),
        "video": video, "frames_zip": frames_zip,
        "record_method": rec.method, "video_frames": rec.frame_count,
    }
    jp, hp = report.generate(out_dir, log, meta)
    vs = log.violations()
    print("\n===== 监考完成 =====")
    print("事件总数: %d，违规: %d" % (len(log.events), len(vs)))
    print("报告: %s\n数据: %s\n录像: %s" % (hp, jp, video))
