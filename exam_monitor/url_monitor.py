# -*- coding: utf-8 -*-
"""浏览器 URL 合规监控。

只允许访问 https://hydro.ac/d/<域>/contest/<比赛id>/... 下的页面；
登录/静态资源等辅助主机在 EXTRA_ALLOWED_HOSTS 中放行。

实现方式（尽力而为，多层兜底）：
1. 以 --app=<比赛URL> 模式启动 Chrome/Edge —— 单窗口无地址栏，天然限制导航；
2. 轮询浏览器 Session/Tabs 快照文件解析当前打开的 URL，发现越界即记录违规，
   并通过命令行让浏览器强制把该标签页导航回比赛首页；
3. 读不到 URL 时（Firefox/Safari），依赖录屏 + 前台窗口标题中的网址做提示，
   并在报告中说明该环境只能人工核查。
"""

import re
import threading
import time
from urllib.parse import urlparse

from . import config, platform_adapter


def is_url_allowed(url, domain, cid):
    """判断 url 是否在允许范围内。返回 (bool, reason)。"""
    try:
        p = urlparse(url)
    except ValueError:
        return False, "无法解析"
    if p.scheme not in ("http", "https"):
        return False, "非 http(s) 协议"
    host = (p.hostname or "").lower()
    if host == "hydro.ac" or host.endswith(".hydro.ac"):
        if host != "hydro.ac":
            return True, "hydro 子域(登录/资源)"
        path = p.path or "/"
        # 允许的前缀：/d/<域>/contest/<cid>
        allow_prefix = "/d/%s/contest/%s" % (domain, cid)
        if path == allow_prefix or path.startswith(allow_prefix + "/") \
                or path.startswith(allow_prefix + "?"):
            return True, "比赛页面"
        # 同域下的其它比赛一律禁止（可能借道偷看别的比赛）
        m = re.match(r"^/d/([^/]+)/contest(?:/|$)", path)
        if m:
            return False, "越界路径(其它比赛): %s" % path
        # 比赛域名下允许登录跳转与站点通用资源
        generic = ("/login", "/logout", "/user/", "/profile", "/static/",
                   "/api/", "/favicon.ico", "/robots.txt",
                   "/contestlist", "/d/%s/" % domain)
        for g in generic:
            if path.startswith(g):
                return True, "站内通用页面"
        return False, "越界路径: %s" % path
    if host in config.EXTRA_ALLOWED_HOSTS:
        return True, "白名单辅助主机"
    return False, "外部站点: %s" % host


class UrlMonitor(threading.Thread):
    """周期读取浏览器打开的 URL，越界 -> on_violation(url, browser)。"""

    def __init__(self, contest_url, domain, cid,
                 on_violation, poll=config.TAB_POLL_INTERVAL):
        super().__init__(daemon=True)
        self.contest_url = contest_url
        self.domain = domain
        self.cid = cid
        self.on_violation = on_violation
        self.poll = poll
        self._stop = threading.Event()
        self._reported = set()   # 已上报过的 url，避免刷屏
        self.enabled = True

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                if self.enabled:
                    self._scan_once()
            except Exception as e:
                print("[url_monitor] error:", e, flush=True)
            self._stop.wait(self.poll)

    def _scan_once(self):
        opened = platform_adapter.get_browser_open_urls()
        for browser, urls in opened.items():
            for u in urls:
                ok, reason = is_url_allowed(u, self.domain, self.cid)
                if ok:
                    continue
                key = (browser, u)
                if key in self._reported:
                    continue
                self._reported.add(key)
                try:
                    self.on_violation(u, browser, reason)
                except Exception as e:
                    print("[url_monitor] cb error:", e, flush=True)
