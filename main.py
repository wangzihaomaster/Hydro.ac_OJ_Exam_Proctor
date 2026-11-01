# -*- coding: utf-8 -*-
"""Hydro OJ 监考系统 —— 零依赖启动脚本。

直接双击运行（Windows 上可另存为 启动.bat：
    @echo off
    start "" pythonw main.py
或
    python main.py
）：

- 不需要安装任何第三方 Python 包；只要电脑装有 Python 3.7+
  （tkinter 随官方安装包自带）即可打开图形界面。
- 录屏、进程监控、Firefox/Edge/Chrome URL 读取全部自动探测环境，
  缺什么库就降级到什么方式，并在报告中如实注明。
- 可选增强（不装也能跑）：
    pip install psutil mss opencv-python numpy lz4 pywin32
    以及系统级 ffmpeg（强烈推荐，用于高质量 mp4 录像）。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_gui():
    from exam_monitor.gui import run
    run()


def run_cli(args):
    from exam_monitor.cli import cli_main
    cli_main(args.domain, args.cid, args.minutes, args.out,
             auto_close=args.auto_close)


def main():
    ap = argparse.ArgumentParser(description="Hydro OJ 监考系统")
    ap.add_argument("--cli", action="store_true", help="命令行模式（无 GUI）")
    ap.add_argument("--domain", help="比赛域，如 myschool")
    ap.add_argument("--cid", help="比赛 ID")
    ap.add_argument("--minutes", type=float, default=120, help="考试时长(分钟)")
    ap.add_argument("--out", default="exam_records", help="输出目录")
    ap.add_argument("--auto-close", action="store_true",
                    help="发现禁用软件直接强制关闭，不询问")
    ns = ap.parse_args()

    if ns.cli or (os.environ.get("DISPLAY", "") == "" and
                  sys.platform not in ("win32", "darwin")):
        if not (ns.domain and ns.cid):
            ns.domain = input("请输入域(domain): ").strip()
            ns.cid = input("请输入比赛ID(contest id): ").strip()
        run_cli(ns)
    else:
        try:
            run_gui()
        except Exception as e:  # 无 tkinter 的 Linux 发行版等
            print("[warn] 图形界面不可用(%s)，切换到命令行模式。" % e)
            if not (ns.domain and ns.cid):
                ns.domain = input("请输入域(domain): ").strip()
                ns.cid = input("请输入比赛ID(contest id): ").strip()
            run_cli(ns)


if __name__ == "__main__":
    main()
