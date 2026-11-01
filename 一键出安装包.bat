@echo off
rem ====================================================================
rem  在任意装有 Python 3.7+ 的电脑上双击此文件，即可生成 Windows 安装包
rem  产物：dist\HydroExamMonitor-Setup.exe（目标电脑无需安装 Python）
rem ====================================================================
setlocal
where python >nul 2>nul || (echo 本机需要 Python 3.7+ 用于打包（考生电脑不需要）& pause & exit /b 1)
echo [1/2] 下载官方免安装嵌入式 Python（约 11MB，内置进安装包，考生全程无需联网）...
powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12';Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-embed-amd64.zip' -OutFile '%TEMP%\py-embed.zip'" || (echo 下载失败，将改为安装时联网模式 & python make_installer.py & goto :done)
echo [2/2] 打包中...
python make_installer.py --embed-zip "%TEMP%\py-embed.zip"
:done
echo.
echo 完成！请把 dist\HydroExamMonitor-Setup.exe 发给考生，双击安装即可，无需任何环境。
pause
