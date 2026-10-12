@echo off
chcp 65001 >nul 2>&1
echo 正在检查并安装 wechat-self-analysis 所需的 Python 依赖...
echo.

REM 优先用 python，没有就退而用 py 启动器
set "PY=python"
where python >nul 2>nul
if errorlevel 1 (
    set "PY=py"
    where py >nul 2>nul
    if errorlevel 1 (
        echo [错误] 未找到 python 或 py。请先安装 Python 3.11+ 并勾选"Add to PATH"。
        pause
        exit /b 1
    )
)

"%PY%" "%~dp0scripts\install_deps.py"
set RC=%errorlevel%

echo.
if %RC%==0 (
    echo 依赖就绪。下一步：确认微信已登录，运行 scripts/dump_chats.py 导出。
) else (
    echo 安装脚本未能完成，请按上面的提示手动处理。
)
pause
exit /b %RC%
