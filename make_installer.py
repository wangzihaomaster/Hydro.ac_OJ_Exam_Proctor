#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hydro OJ 监考系统 —— Windows 安装包生成器（跨平台，仅用 Python 标准库）

产出两个免环境的分发物：
  dist/HydroExamMonitor-Setup.exe   自解压单文件安装程序（双击→自动装到 %LOCALAPPDATA%\\HydroExamMonitor→创建桌面快捷方式→启动）
  dist/HydroExamMonitor-Windows.zip 绿色便携包（解压即用，含卸载.bat）

原理：真正的 exe 由一个极小的自解压引导器(_stub) + 打包好的 zip 载荷拼接而成。
      目标电脑无需安装 Python——引导器运行时从 python.org 官方嵌入式发行版
      (embeddable, ~15MB, 免安装) 获取运行时并静默配置；载荷本身零第三方依赖。

用法：python3 make_installer.py            # 联网取官方嵌入包装版（推荐，产物~30MB）
      python3 make_installer.py --embed-zip 已下载的python-3.x.x-embed-amd64.zip
"""
import argparse
import hashlib
import io
import os
import zipfile

EMBED_VERSION = "3.12.7"
EMBED_URL = f"https://www.python.org/ftp/python/{EMBED_VERSION}/python-{EMBED_VERSION}-embed-amd64.zip"

SRC_FILES = [
    "main.py", "requirements.txt", "README.md",
    "exam_monitor/__init__.py", "exam_monitor/config.py", "exam_monitor/events.py",
    "exam_monitor/platform_adapter.py", "exam_monitor/app_monitor.py",
    "exam_monitor/url_monitor.py", "exam_monitor/recorder.py",
    "exam_monitor/report.py", "exam_monitor/gui.py", "exam_monitor/cli.py",
]

STUB = r'''@echo off
setlocal EnableDelayedExpansion
rem =====================================================================
rem  Hydro OJ 监考系统 安装程序（自解压引导器，无需目标机预装任何环境）
rem =====================================================================
title Hydro OJ 监考系统 - 安装
set "PYV=3.12.7"
set "PYURL=https://www.python.org/ftp/python/%PYV%/python-%PYV%-embed-amd64.zip"
set "TARGET=%LOCALAPPDATA%\HydroExamMonitor"
set "SELF=%~f0"
set "TMPD=%TEMP%\hydro_exam_setup_%RANDOM%"
mkdir "%TMPD%" 2>nul

echo [1/4] 正在释放安装数据...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f=[IO.File]::ReadAllBytes('%SELF%');$m=[Text.Encoding]::ASCII.GetString($f[($f.Length-4)..($f.Length-1)]);if($m -ne 'HZPY'){throw 'magic'};$len=[BitConverter]::ToInt64($f,$f.Length-12);$start=$f.Length-12-$len;$fs=[IO.File]::Create('%TMPD%\payload.zip');$fs.Write($f,$start,$len);$fs.Close()"
if errorlevel 1 goto :fail_extract
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%TMPD%\payload.zip' -DestinationPath '%TMPD%\app' -Force"
if errorlevel 1 goto :fail_unzip

echo [2/4] 准备 Python 运行环境（首次需联网下载约 15MB，稍候片刻）...
set "PYOK="
for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYOK (
    "%%P" -c "print(1)" >nul 2>nul && set "PYEXE=%%P" && set "PYOK=1"
)
if not defined PYOK for /f "delims=" %%P in ('where py 2^>nul') do if not defined PYOK (
    "%%P" -3 -c "print(1)" >nul 2>nul && set "PYEXE=%%P -3" && set "PYOK=1"
)
if not defined PYOK (
    if exist "%TMPD%\app\python-embed.zip" (
        copy /y "%TMPD%\app\python-embed.zip" "%TMPD%\py.zip" >nul
        echo     使用安装包内置的离线 Python（无需联网）
    ) else if exist "%~dp0python-embed.zip" (
        copy /y "%~dp0python-embed.zip" "%TMPD%\py.zip" >nul
        echo     使用同目录下的离线 python-embed.zip
    ) else (
        echo     正在下载官方免安装嵌入式 Python %PYV% ...
        powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12';Invoke-WebRequest -Uri '%PYURL%' -OutFile '%TMPD%\py.zip'"
        if errorlevel 1 goto :fail_net
    )
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%TMPD%\py.zip' -DestinationPath '%TARGET%\python' -Force"
    if errorlevel 1 goto :fail_unzip
    del "%TMPD%\py.zip" 2>nul
    set "PYEXE=%TARGET%\python\python.exe"
    rem 启用 site-packages 支持，便于日后 pip 安装可选增强组件
    powershell -NoProfile -Command "(Get-Content '%TARGET%\python\python312._pth') -replace '^#\s*import site','import site' | Set-Content '%TARGET%\python\python312._pth'"
)

echo [3/4] 安装到 %TARGET% ...
robocopy "%TMPD%\app" "%TARGET%" /E /NFL /NDL /NJH /NJS >nul
if errorlevel 8 goto :fail_copy
>"%TARGET%\launcher.cmd" echo @echo off
>>"%TARGET%\launcher.cmd" echo start "" /min "%PYEXE%" "%TARGET%\main.py"
>>"%TARGET%\launcher.cmd" echo exit
set "LNK=%USERPROFILE%\Desktop\Hydro OJ 监考系统.lnk"
powershell -NoProfile -Command "$w=New-Object -ComObject WScript.Shell;$l=$w.CreateShortcut('%LNK%');$l.TargetPath='%TARGET%\launcher.cmd';$l.WorkingDirectory='%TARGET%';$l.Save()"
for /f "delims=" %%D in ('powershell -NoProfile -Command "[Environment]::GetFolderPath('Startup')"') do set "STARTUPD=%%D"
copy /y "%LNK%" "%STARTUPD%\" >nul 2>nul

echo [4/4] 完成！正在启动 Hydro OJ 监考系统 ...
rd /s /q "%TMPD%" 2>nul
start "" cmd /c "%TARGET%\launcher.cmd"
echo 桌面已创建快捷方式「Hydro OJ 监考系统」，卸载请删除该目录后清理快捷方式。
timeout /t 3 >nul
exit /b 0

:fail_extract
echo [错误] 安装数据读取失败，文件可能不完整，请重新下载安装包。
pause & exit /b 1
:fail_unzip
echo [错误] 解压失败，请确认磁盘空间充足且杀毒软件未拦截。
pause & exit /b 1
:fail_net
echo [错误] 无法下载 Python 运行环境。请在有网电脑上下载
echo        %PYURL%
echo        放到本程序同目录并命名为 python-embed.zip 后重试。
pause & exit /b 1
:fail_copy
echo [错误] 复制文件失败，请关闭正在运行的监考程序后重试。
pause & exit /b 1
'''


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def build_payload(embed_zip_bytes=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in SRC_FILES:
            if os.path.exists(rel):
                z.write(rel, rel.replace(os.sep, "/"))
            else:
                print("警告: 缺少文件", rel)
        if embed_zip_bytes is not None:
            z.writestr("python-embed.zip", embed_zip_bytes)
            z.writestr("INSTALL_NOTE.txt",
                       "本安装包已内置官方免安装嵌入式 Python %s，安装全程无需联网。" % EMBED_VERSION)
        else:
            z.writestr("INSTALL_NOTE.txt",
                       "Python 运行时将在安装时从 python.org 官方站点下载（约15MB）。")
    return buf.getvalue()


def assemble_exe(stub_text, payload):
    # 布局: [bat引导器(gbk)] [zip载荷] [载荷长度 int64 LE] [b"HZPY"]
    stub = stub_text.replace("\n", "\r\n").encode("gbk")
    return stub + payload + len(payload).to_bytes(8, "little") + b"HZPY"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed-zip", help="本地已下载的 python-x.y.z-embed-amd64.zip，内置进安装包（离线安装）")
    args = ap.parse_args()
    embed_bytes = None
    if args.embed_zip:
        with open(args.embed_zip, "rb") as f:
            embed_bytes = f.read()
        print("已加载嵌入式 Python: %.1f MB" % (len(embed_bytes) / 1e6))
    payload = build_payload(embed_bytes)
    exe = assemble_exe(STUB, payload)
    os.makedirs("dist", exist_ok=True)
    out_exe = os.path.join("dist", "HydroExamMonitor-Setup.exe")
    with open(out_exe, "wb") as f:
        f.write(exe)
    print("已生成", out_exe, "(%.1f MB)" % (len(exe) / 1e6), "sha256:", sha256(exe)[:16])

    # 绿色便携 zip 包
    out_zip = os.path.join("dist", "HydroExamMonitor-Windows.zip")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in SRC_FILES:
            if os.path.exists(rel):
                z.write(rel, ("HydroExamMonitor/" + rel).replace(os.sep, "/"))
        z.writestr("HydroExamMonitor/启动.bat", open("启动.bat", encoding="utf-8").read())
        z.writestr("HydroExamMonitor/卸载.bat",
                   "@echo off\r\nrd /s /q \"%LOCALAPPDATA%\\HydroExamMonitor\"\r\ndel \"%USERPROFILE%\\Desktop\\Hydro OJ 监考系统.lnk\"\r\necho 已卸载。\r\npause\r\n")
        z.writestr("HydroExamMonitor/说明.txt",
                   "绿色便携版：若电脑装有 Python 3.7+，双击 启动.bat 即可；\r\n"
                   "否则请使用同目录的 HydroExamMonitor-Setup.exe 一键安装（自动补齐免安装Python）。")
    print("已生成", out_zip)


if __name__ == "__main__":
    main()
