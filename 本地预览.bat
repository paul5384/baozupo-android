@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==========================================
echo   包租婆出租屋管家 安卓版 - 电脑预览
echo ==========================================
echo.
echo 第一次运行前请先安装 Kivy：
echo     pip install kivy
echo.
python -c "import kivy" 2>nul
if errorlevel 1 (
    echo [!] 没有检测到 Kivy，正在自动安装...
    python -m pip install kivy
)
echo.
echo 正在启动，窗口大小按手机比例模拟...
python main.py
pause
