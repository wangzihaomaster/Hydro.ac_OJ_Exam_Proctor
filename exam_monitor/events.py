# -*- coding: utf-8 -*-
"""监考事件模型与线程安全的事件日志。"""

import json
import os
import threading
import time
from datetime import datetime


def fmt_ts(ts):
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


class Event:
    """一条监考事件。

    kind 取值:
      session_start / session_end   考试开始、结束
      video                         录屏状态
      app_open                      检测到非白名单软件打开（违规）
      app_close                     违规软件被关闭
      app_forced                    违规软件被强制关闭
      app_allowed                   白名单软件打开（仅记录）
      url_violation                 浏览器访问了非比赛 URL（违规）
      url_block                     违规页面已被强制导航回比赛页
      browser_launch                启动默认浏览器
      warning                       其他警告
      info                          普通信息
    """

    __slots__ = ("ts", "kind", "message", "detail", "ack", "result")

    def __init__(self, ts, kind, message, detail=None, ack=""):
        self.ts = ts
        self.kind = kind
        self.message = message
        self.detail = detail or {}
        self.ack = ack  # 用户对弹窗的回答: close/keep/timeout/auto
        self.result = None  # 后台线程等待 UI 回答的槽位（None=未处理）

    def to_dict(self):
        return {
            "time": fmt_ts(self.ts),
            "ts": self.ts,
            "kind": self.kind,
            "message": self.message,
            "detail": self.detail,
            "ack": self.ack,
        }


class EventLog:
    """线程安全的事件记录器，同时写入 monitor.log 与内存列表。"""

    def __init__(self, log_path=None):
        self._lock = threading.Lock()
        self.events = []
        self._log_path = log_path
        self._start_ts = time.time()

    @property
    def elapsed(self):
        return time.time() - self._start_ts

    def record(self, kind, message, detail=None, ack=""):
        ev = Event(time.time(), kind, message, detail, ack)
        with self._lock:
            self.events.append(ev)
        line = "[{}] {:<16} {}".format(fmt_ts(ev.ts), kind, message)
        if ack:
            line += "  (处理: {})".format(ack)
        print(line, flush=True)
        if self._log_path:
            try:
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass
        return ev

    # ---- 便捷方法 ----
    def violation(self, kind, message, detail=None, ack=""):
        assert kind in ("app_open", "url_violation"), kind
        return self.record(kind, message, detail, ack)

    def info(self, message, detail=None):
        return self.record("info", message, detail)

    def warning(self, message, detail=None):
        return self.record("warning", message, detail)

    def violations(self):
        with self._lock:
            return [e for e in self.events
                    if e.kind in ("app_open", "url_violation")]

    def dump_json(self, path, meta):
        with self._lock:
            data = {
                "meta": meta,
                "generated_at": fmt_ts(time.time()),
                "events": [e.to_dict() for e in self.events],
            }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path
