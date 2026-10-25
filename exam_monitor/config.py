# -*- coding: utf-8 -*-
"""全局配置：白名单、URL 规则、录屏参数等。"""

APP_NAME = "Hydro 监考系统"
VERSION = "1.0.0"

# 允许在前台运行的软件（进程名关键字 -> 显示名称）
ALLOWED_PROCESSES = {
    # ---- IDE / 编译器 ----
    "idea":            "IntelliJ IDEA",
    "intellij":        "IntelliJ IDEA",
    "studio64":        "Dev-C++ (Code::Blocks)",
    "devcpp":          "Dev-C++",
    "devenv":          "Visual Studio",
    "vcexpress":       "Visual C++ Express",
    "vsswin32":        "旧版 Visual C++ 6.0",
    "cl":              "MSVC 编译器 cl.exe",
    "msbuild":         "MSBuild",
    "gcc":             "GCC",
    "g++":             "G++",
    "mingw32-make":    "MinGW make",
    "code":            "VS Code",
    "pycharm":         "PyCharm",
    # ---- 画图 ----
    "mspaint":         "画图",
    "paintnet":        "Paint.NET",
    # ---- 浏览器 ----
    "chrome":          "Chrome",
    "firefox":         "Firefox",
    "msedge":          "Microsoft Edge",
    "edge":            "Microsoft Edge",
    "opera":           "Opera",
    "brave":           "Brave",
    "safari":          "Safari",
    # ---- 系统/监考自身（不记录违规）----
    "explorer":        "Windows 资源管理器(系统)",
    "taskmgr":         "任务管理器",
    "wininit":         "系统进程",
    "winlogon":        "系统进程",
    "services":        "系统服务",
    "svchost":         "系统服务",
    "lsass":           "系统进程",
    "csrss":           "系统进程",
    "smss":            "系统进程",
    "dwm":             "桌面窗口管理器",
    "fontdrvhost":     "系统进程",
    "runtimebroker":   "系统进程",
    "searchindexer":   "系统搜索",
    "ctfmon":          "输入法",
    "textinputhost":   "输入体验",
    "python":          "Python(本程序)",
    "pythonw":         "Python(本程序)",
    "conhost":         "控制台主机",
    "cmd":             "命令行",
    "powershell":      "PowerShell",
    "windowsterminal": "终端",
}

# 静默忽略的进程（不计入违规，也不弹窗）
IGNORED_PROCESSES = {
    "System", "Registry", "Memory Compression", "Secure System",
}

# Hydro OJ 域名
HYDRO_BASE = "https://hydro.ac"

# URL 前缀模板：域 + 比赛 id 确定后，只允许访问此前缀下的页面
CONTEST_URL_TEMPLATE = HYDRO_BASE + "/d/{domain}/contest/{cid}"

# 额外允许访问的主机（登录、静态资源等）
EXTRA_ALLOWED_HOSTS = {
    "accounts.google.com",
    "open.weixin.qq.com",
    "passport.hydro.ac",
    "cdn.jsdelivr.net",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
}

# 录屏参数
SCREEN_FPS = 1.0                 # 每秒截图帧数
VIDEO_FOURCC = "mp4v"            # OpenCV 编码（mp4v -> .mp4，无外部依赖）
JPEG_QUALITY = 80                # 帧 JPEG 质量

# 浏览器标签页监控轮询间隔（秒）
TAB_POLL_INTERVAL = 2.0

# 报告文件名
REPORT_JSON = "report.json"
REPORT_HTML = "monitor_report.html"
LOG_FILE = "monitor.log"
VIDEO_FILE = "screen.mp4"
FRAMES_DIR = "frames"
FRAMES_ZIP = "frames.zip"
