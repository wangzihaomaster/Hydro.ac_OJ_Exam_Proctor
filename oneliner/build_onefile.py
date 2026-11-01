#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 HydroExamMonitor 源码打包成"单个 .py 文件"（免安装、双击即用）。
用法：python3 build_onefile.py            # 生成 HydroExamMonitor-onefile.py
考生电脑只需装有 Python 3.7+，直接：python HydroExamMonitor-onefile.py
GUI 优先（tkinter），无 GUI 环境自动 CLI。
"""
import base64, os, textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)  # 仓库根目录

FILES = [
    "main.py",
    "exam_monitor/__init__.py",
    "exam_monitor/config.py",
    "exam_monitor/events.py",
    "exam_monitor/platform_adapter.py",
    "exam_monitor/recorder.py",
    "exam_monitor/app_monitor.py",
    "exam_monitor/url_monitor.py",
    "exam_monitor/report.py",
    "exam_monitor/gui.py",
    "exam_monitor/cli.py",
]

def main():
    entries = []
    for rel in FILES:
        p = os.path.join(ROOT, rel)
        with open(p, "rb") as f:
            data = f.read()
        entries.append((rel.replace("\\", "/"), base64.b64encode(data).decode()))

    lines = []
    lines.append("#!/usr/bin/env python3")
    lines.append("# -*- coding: utf-8 -*-")
    lines.append('"""HydroExamMonitor 单文件版：内嵌全部源码，无需第三方包。"""')
    lines.append("import base64, importlib.util, os, sys, tempfile")
    lines.append("")
    lines.append("_BUNDLE = {")
    for rel, b64 in entries:
        # 每行 96 字符折行，避免超长行
        chunks = [b64[i:i+96] for i in range(0, len(b64), 96)]
        if chunks:
            body = "".join('        "%s"\n' % c for c in chunks)
            lines.append('    "%s": (\n%s    ),' % (rel, body))
        else:
            lines.append('    "%s": "",' % rel)
    lines.append("}")
    lines.append(textwrap.dedent('''
        def _materialize():
            """把内嵌源码释放到临时目录，返回包根路径。"""
            root = os.path.join(tempfile.gettempdir(), "hydro_exam_monitor_app")
            for rel, b64 in _BUNDLE.items():
                dst = os.path.join(root, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(dst, "wb") as f:
                    f.write(base64.b64decode(b64))
            return root

        def main():
            root = _materialize()
            if root not in sys.path:
                sys.path.insert(0, root)
            spec = importlib.util.spec_from_file_location("__main_app__", os.path.join(root, "main.py"))
            mod = importlib.util.module_from_spec(spec)
            sys.argv[0] = "HydroExamMonitor"
            spec.loader.exec_module(mod)
            mod.main()

        if __name__ == "__main__":
            main()
        '''))
    out = os.path.join(ROOT, "HydroExamMonitor-onefile.py")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("WROTE", out, os.path.getsize(out), "bytes")

if __name__ == "__main__":
    main()
