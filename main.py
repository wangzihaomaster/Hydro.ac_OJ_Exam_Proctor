#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hydro OJ 监考系统 —— 入口。

用法：
    python main.py                 # 图形界面（推荐）
    python main.py --cli ...       # 命令行/无图形环境模式
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

    if ns.cli or os.environ.get("DISPLAY", "") == "" and \
            sys.platform not in ("win32", "darwin"):
        if not (ns.domain and ns.cid):
            ns.domain = input("请输入域(domain): ").strip()
            ns.cid = input("请输入比赛ID(contest id): ").strip()
        run_cli(ns)
    else:
        run_gui()


if __name__ == "__main__":
    main()
