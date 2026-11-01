@echo off
rem ============================================================
rem  打包成免环境的单文件 exe（HydroExamMonitor.exe）
rem  只需执行一次，之后把生成的 dist\HydroExamMonitor.exe
rem  拷到任何 Windows 电脑双击即可运行，无需安装 Python。
rem  需要联网下载 pyinstaller（pip）。
rem ============================================================
python -m pip install --upgrade pyinstaller || goto :err
python -m PyInstaller --onefile --windowed --name HydroExamMonitor ^
  --hidden-import tkinter --hidden-import tkinter.ttk ^
  --collect-submodules exam_monitor main.py || goto :err
echo.
echo 打包完成：dist\HydroExamMonitor.exe  （单文件，免环境直接双击运行）
goto :eof
:err
echo 打包失败，请检查上方错误信息（确认已安装 Python 并可访问 pip 源）。
exit /b 1
