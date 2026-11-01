@echo off
rem Hydro OJ 监考系统 —— Windows 双击启动（需已安装 Python 3.7+）
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0main.py"
) else (
    python "%~dp0main.py"
)
