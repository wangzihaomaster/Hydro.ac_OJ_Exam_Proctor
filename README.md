# Hydro OJ 监考系统（hydro-exam-monitor）

针对 [hydro.ac](https://hydro.ac) 在线编程考试的桌面监考证照工具。
启动时输入「域」和「比赛 ID」（网址 = `https://hydro.ac/d/<域>/contest/<比赛id>`），考试期间：

1. **全程录屏**：ffmpeg（Windows=gdigrab / Linux=x11grab / macOS=avfoundation），
   无 ffmpeg 时自动降级 mss+OpenCV 逐帧录制，并同时保存 JPEG 帧序列 zip 备份；
2. **禁止打开其它软件**：每秒扫描进程与前台窗口，白名单仅保留
   IDEA、Dev-C++、Visual C++/VS、画图、浏览器及系统进程；
   发现违规软件弹窗提示"是否关闭"，拒绝则留档，超时自动强关；
3. **浏览器只允许访问比赛页面**：
   - Chrome / Edge / Chromium：`--app=<比赛URL>` 无地址栏模式启动；
   - **Firefox：`--kiosk` 全屏锁定比赛页**，并向安装目录写入企业策略文件
     （可写时生效）；
   - 后台轮询读取浏览器打开的 URL，越界即记录违规并重新拉回比赛页。

## 支持的浏览器 URL 读取
| 浏览器 | 方式 |
|---|---|
| Chrome / Edge / Chromium / Opera / Brave | profile 的 `Session_*` / `Tabs_*` 快照 + 窗口标题兜底 |
| **Firefox** | `sessionstore.jsonlz4`（Mozilla LZ4 帧格式，lz4 库解压，结构化提取每个标签当前页；无 lz4 库时正则兜底）+ 窗口标题兜底 |

Edge 在 Windows 上进程名为 `msedge.exe`、profile 位于
`%LOCALAPPDATA%\Microsoft\Edge\User Data\Default`（含 `Profile 1` 等多配置目录），
Linux 为 `~/.config/microsoft-edge`，均已适配；Firefox profile 通过
`profiles.ini` 或 `*.default*` 目录自动定位（Win/Linux/macOS 路径全覆盖）。

## 运行
```bash
pip install -r requirements.txt
python main.py                 # GUI：输入域与比赛ID -> 开始考试 -> 结束考试导出报告
python main.py --cli --domain myschool --cid ctest001 --minutes 120 [--auto-close]
```

结束时自动导出监考档案目录：`monitor_report.html`（可视化报告）、
`report.json`、`monitor.log`、`screen.mp4`、`frames.zip`。

## 已知限制
- Session 快照存在写入延迟，极端快速跳转可能漏采——所有行为仍会留在录屏中；
- Firefox `--kiosk` 下按 Ctrl+Q/Alt+F4 仍可退出，配合系统级组策略更安全；
- 本工具为"尽力而为"软监考，无法阻止手机等外部设备作弊，证据供事后追责。

## 免环境直接启用（零依赖模式）★
本软件**不需要 pip 安装任何第三方包**即可直接运行——所有功能模块都做了
自动探测与降级：

| 功能 | 有增强库/工具时 | 什么都没有时（零依赖） |
|---|---|---|
| 录屏 | ffmpeg → mp4；或 mss+OpenCV → mp4+帧序列 | Pillow/scrot/screencap/ImageMagick 定时截 PNG 帧序列；全都没有则报告注明并跳过录像 |
| 进程监控 | psutil | Windows: CreateToolhelp32Snapshot(ctypes)；Linux: /proc；macOS: ps 命令 |
| 强制关闭 | psutil terminate/kill | Windows: TerminateProcess；POSIX: SIGTERM→SIGKILL |
| Firefox URL | lz4 库解压 sessionstore.jsonlz4 | **内置纯 Python LZ4 block 解码器**（已验证），再不行正则兜底 |
| Edge/Chrome URL | Session/Tabs 快照 + 窗口标题 | 同左（本就只用标准库） |
| GUI | tkinter（官方 Python 安装包自带） | 自动切换命令行模式 |

### 三种启动方式
```text
1) 装了 Python（3.7+，官网安装包即可）：
   双击  启动.bat        （Windows，优先 pythonw 无黑窗）
   或    python main.py

2) 完全免环境 exe（目标电脑连 Python 都不用装）：
   在任意一台开发机上双击 build_exe.bat 一次，
   生成 dist\HydroExamMonitor.exe —— 单文件、拷贝即用。

3) 可选增强（提升录像质量与效率，不装也能跑）：
   pip install psutil mss opencv-python numpy lz4 pywin32
   + 系统安装 ffmpeg 并加入 PATH（强烈推荐，得到完整 mp4 录像）
```
