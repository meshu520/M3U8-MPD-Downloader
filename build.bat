@echo off
chcp 65001 >nul
echo ========================================
echo   M3U8/MPD视频下载助手 v1.0.0 - 打包脚本
echo   GUI独立EXE，不内置工具
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.11
    pause
    exit /b 1
)

echo [1/3] 安装依赖...
pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo [2/3] 清理旧的构建文件...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "M3U8视频下载助手.spec" del /q "M3U8视频下载助手.spec"

echo.
echo [3/3] 开始打包 EXE (onefile + windowed)...
echo 注意: 不使用 --add-data，不内置 N_m3u8DL-RE / mp4decrypt / ffmpeg
echo.
pyinstaller ^
    --onefile ^
    --windowed ^
    --name "M3U8视频下载助手" ^
    main.py

if errorlevel 1 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo   打包完成！
echo   输出: dist\M3U8视频下载助手.exe
echo.
echo   发布目录结构:
echo   M3U8视频下载助手\
echo   ├── M3U8视频下载助手.exe
echo   ├── N_m3u8DL-RE(6).exe   (自行放入)
echo   ├── mp4decrypt.exe       (自行放入)
echo   ├── ffmpeg.exe           (自行放入)
echo   ├── config.json          (首次运行自动生成)
echo   └── logs\                (保存日志后自动生成)
echo.
echo   GUI EXE启动后自动扫描同目录工具，
echo   缺少工具时弹窗提示选择。
echo ========================================
echo.
pause
