# -*- coding: utf-8 -*-
"""监考报告生成：report.json + 自包含 HTML 报告（含事件时间线、违规统计、录像链接）。"""

import os
from datetime import datetime

from . import config
from .events import fmt_ts


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


KIND_LABEL = {
    "session_start": ("考试开始", "#2e7d32"),
    "session_end": ("考试结束", "#2e7d32"),
    "video": ("录屏", "#1565c0"),
    "app_open": ("违规：打开禁用软件", "#c62828"),
    "app_close": ("软件已关闭", "#ef6c00"),
    "app_forced": ("软件被强制关闭", "#ef6c00"),
    "app_allowed": ("允许的软件", "#2e7d32"),
    "url_violation": ("违规：访问越界网址", "#ad1457"),
    "url_block": ("越界页面已重置", "#ef6c00"),
    "browser_launch": ("启动浏览器", "#1565c0"),
    "warning": ("警告", "#ef6c00"),
    "info": ("信息", "#455a64"),
}

ACK_LABEL = {
    "close": "用户选择关闭",
    "keep": "用户选择不关闭(已记录)",
    "timeout": "超时未处理，系统自动关闭",
    "auto": "系统自动关闭",
    "": "—",
}


def build_html(meta, events, out_files_desc):
    violations = [e for e in events if e.kind in ("app_open", "url_violation")]
    n_app = sum(1 for e in violations if e.kind == "app_open")
    n_url = sum(1 for e in violations if e.kind == "url_violation")
    dur_min = meta.get("duration", 0) / 60.0

    rows = []
    for e in events:
        label, color = KIND_LABEL.get(e.kind, (e.kind, "#000"))
        detail = ""
        if e.detail:
            detail = "; ".join("%s=%s" % (k, v) for k, v in e.detail.items())
        rows.append(
            "<tr class='{cls}'><td>{t}</td>"
            "<td><span class='tag' style='background:{c}'>{lab}</span></td>"
            "<td>{msg}</td><td class='dim'>{det}</td><td>{ack}</td></tr>".format(
                cls="viol" if e.kind in ("app_open", "url_violation") else "",
                t=_esc(fmt_ts(e.ts)), c=color, lab=_esc(label),
                msg=_esc(e.message), det=_esc(detail),
                ack=_esc(ACK_LABEL.get(e.ack, e.ack or "—"))))

    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>监考报告 - {domain}/{cid}</title><style>
body{{font-family:"Microsoft YaHei",sans-serif;margin:24px;color:#222;background:#fafafa}}
h1{{font-size:22px}} .grid{{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0}}
.card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:14px 20px;min-width:160px;
box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.card b{{font-size:24px;display:block}} .bad{{color:#c62828}} .ok{{color:#2e7d32}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
th,td{{border-bottom:1px solid #eee;padding:6px 10px;text-align:left;vertical-align:top}}
th{{background:#f0f0f0}} tr.viol{{background:#fff3f3}}
.tag{{color:#fff;border-radius:4px;padding:2px 8px;font-size:12px;white-space:nowrap}}
.dim{{color:#777}} ul li{{margin:4px 0}}
</style></head><body>
<h1>📋 Hydro OJ 监考报告</h1>
<div class="grid">
 <div class="card">比赛地址<b style="font-size:14px">{url}</b></div>
 <div class="card">考试时长<b>{dur:.1f} 分钟</b></div>
 <div class="card">违规·禁用软件<b class="{appcls}">{n_app}</b></div>
 <div class="card">违规·越界网址<b class="{urlcls}">{n_url}</b></div>
 <div class="card">总事件数<b>{nev}</b></div>
</div>
<p>考生主机：{user}@{host} ｜ 系统：{sys} ｜ 报告生成：{gen}</p>
<h2>事件时间线</h2>
<table><tr><th>时间</th><th>类型</th><th>说明</th><th>详情</th><th>处理</th></tr>
{rows}</table>
<h2>导出文件</h2><ul>{files}</ul>
<p class="dim">本报告由《{app} v{ver}》自动生成。录像见 screen.mp4，
帧序列备份见 frames.zip（每帧文件名 frame_序号.jpg，与时间顺序一致）。</p>
</body></html>""".format(
        domain=_esc(meta["domain"]), cid=_esc(meta["cid"]),
        url=_esc(meta["contest_url"]), dur=dur_min,
        appcls="bad" if n_app else "ok", urlcls="bad" if n_url else "ok",
        n_app=n_app, n_url=n_url, nev=len(events),
        user=_esc(meta.get("user", "?")), host=_esc(meta.get("host", "?")),
        sys=_esc(meta.get("system", "?")),
        gen=_esc(datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        rows="\n".join(rows),
        files="".join("<li>%s</li>" % _esc(f) for f in out_files_desc),
        app=_esc(config.APP_NAME), ver=_esc(config.VERSION))
    return html


def generate(out_dir, log, meta):
    """写 report.json 与 monitor_report.html，返回路径列表。"""
    json_path = os.path.join(out_dir, config.REPORT_JSON)
    log.dump_json(json_path, meta)

    files_desc = []
    for fn, desc in [(config.VIDEO_FILE, "全程录屏视频"),
                     (config.FRAMES_ZIP, "录屏帧序列备份(zip)"),
                     (config.LOG_FILE, "纯文本监控日志"),
                     (config.REPORT_JSON, "结构化事件数据(json)")]:
        p = os.path.join(out_dir, fn)
        if os.path.exists(p):
            size = os.path.getsize(p)
            files_desc.append("%s —— %s (%.1f KB)" % (fn, desc, size / 1024))

    html_path = os.path.join(out_dir, config.REPORT_HTML)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(meta, log.events, files_desc))
    return json_path, html_path
