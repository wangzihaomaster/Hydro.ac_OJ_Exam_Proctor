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

## 单文件免安装版（最简单，推荐）

`HydroExamMonitor-onefile.py` 是一个自包含的 Python 脚本（约 130KB），
内嵌了全部模块源码，**无需下载/解压/安装任何东西**：

```bash
python HydroExamMonitor-onefile.py            # Windows 双击或命令行运行，GUI 优先
python HydroExamMonitor-onefile.py --cli --domain 域 --cid 比赛id --minutes 120
```

要求仅为电脑装有 Python 3.7+（tkinter 随官方安装包自带）。
重新生成：`python oneliner/build_onefile.py`。

## 本地重建安装包（Setup.exe）

1. 把本仓库（或 `HydroExamMonitor-source.zip` 解压）拷到任意一台能上网的电脑；
2. 下载嵌入式 Python：https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip
   保存为仓库根目录 `python-embed.zip`（若已存在则跳过）；
3. Windows：双击 `一键出安装包.bat`；或跨平台命令行：
   ```bash
   python make_installer.py --embed-zip python-embed.zip
   ```
4. 产物在 `dist/HydroExamMonitor-Setup.exe`（以及绿色包 `HydroExamMonitor-Windows.zip`），
   发给考生机双击安装即可，目标机无需 Python、无需联网。

## 安装包（推荐·免环境）

考生电脑**什么都不用装**：把 `dist/HydroExamMonitor-Setup.exe` 拷给考生，双击→自动安装到 `%LOCALAPPDATA%\HydroExamMonitor`→创建桌面快捷方式并启动。

- 生成安装包：在本仓库目录运行 `python3 make_installer.py --embed-zip python-3.12.7-embed-amd64.zip`（或直接双击 `一键出安装包.bat`）；安装包已内置官方免安装嵌入式 Python，考生端全程离线可用。
- 备用绿色包：`dist\HydroExamMonitor-Windows.zip` 解压即用（需机器有 Python 3.7+），含卸载.bat。

## 支持的浏览器 URL 读取
| 浏览器 | 方式 |
|---|---|
| Chrome / Edge / Chromium / Opera / Brave | profile 的 `Session_*` / `Tabs_*` 快照 + 窗口标题兜底 |
| **Firefox** | `sessionstore.jsonlz4`（Mozilla LZ4 帧格式，lz4 库解压，结构化提取每个标签当前页；无 lz4 库时正则兜底）+ 窗口标题兜底 |

Edge 在 Windows 上进程名为 `msedge.exe`、profile 位于
`%LOCALAPPDATA%\Microsoft\Edge\User Data\Default`（含 `Profile 1` 等多配置目录），
Linux 为 `~/.config/microsoft-edge`，均已适配；Firefox profile 通过
`profiles.ini` 或 `*.default*` 目录自动定位（Win/Linux/macOS 路径全覆盖）。

## 安装包（推荐·免环境）

考生电脑**什么都不用装**：把 `dist/HydroExamMonitor-Setup.exe` 拷给考生，双击→自动安装到 `%LOCALAPPDATA%\HydroExamMonitor`→创建桌面快捷方式并启动。

- 生成安装包：在本仓库目录运行 `python3 make_installer.py --embed-zip python-3.12.7-embed-amd64.zip`（或直接双击 `一键出安装包.bat`）；安装包已内置官方免安装嵌入式 Python，考生端全程离线可用。
- 备用绿色包：`dist\HydroExamMonitor-Windows.zip` 解压即用（需机器有 Python 3.7+），含卸载.bat。

## 运行
```bash
pip install -r requirements.txt
python main.py                 # GUI：输入域与比赛ID -> 开始考试 -> 结束考试导出报告
python main.py --cli --domain myschool --cid ctest001 --minutes 120 [--auto-close]
```

结束时自动导出监考档案目录：`monitor_report.html`（可视化报告）、
`report.json`、`monitor.log`、`screen.mp4`、`frames.zip`。

## 安装包（推荐·免环境）

考生电脑**什么都不用装**：把 `dist/HydroExamMonitor-Setup.exe` 拷给考生，双击→自动安装到 `%LOCALAPPDATA%\HydroExamMonitor`→创建桌面快捷方式并启动。

- 生成安装包：在本仓库目录运行 `python3 make_installer.py --embed-zip python-3.12.7-embed-amd64.zip`（或直接双击 `一键出安装包.bat`）；安装包已内置官方免安装嵌入式 Python，考生端全程离线可用。
- 备用绿色包：`dist\HydroExamMonitor-Windows.zip` 解压即用（需机器有 Python 3.7+），含卸载.bat。

## 已知限制
- Session 快照存在写入延迟，极端快速跳转可能漏采——所有行为仍会留在录屏中；
- Firefox `--kiosk` 下按 Ctrl+Q/Alt+F4 仍可退出，配合系统级组策略更安全；
- 本工具为"尽力而为"软监考，无法阻止手机等外部设备作弊，证据供事后追责。

## 安装包（推荐·免环境）

考生电脑**什么都不用装**：把 `dist/HydroExamMonitor-Setup.exe` 拷给考生，双击→自动安装到 `%LOCALAPPDATA%\HydroExamMonitor`→创建桌面快捷方式并启动。

- 生成安装包：在本仓库目录运行 `python3 make_installer.py --embed-zip python-3.12.7-embed-amd64.zip`（或直接双击 `一键出安装包.bat`）；安装包已内置官方免安装嵌入式 Python，考生端全程离线可用。
- 备用绿色包：`dist\HydroExamMonitor-Windows.zip` 解压即用（需机器有 Python 3.7+），含卸载.bat。

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
