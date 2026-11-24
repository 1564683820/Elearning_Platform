@echo off
chcp 65001 >nul
echo ============================================
echo  扫描批卷全链路集成测试 - 运行脚本
echo  使用 uv 环境
echo ============================================
echo.

cd /d "%~dp0.."

:: 检测是否有 uv 虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] 创建 uv 虚拟环境...
    uv venv
    echo [INFO] 安装依赖...
    uv sync
)

echo [1/2] 检查 MySQL 连接...
.venv\Scripts\python -c "from app.db.database import async_session; import asyncio; asyncio.run(async_session().__aenter__())" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] MySQL 连接失败，请检查 MySQL 是否运行
    pause
    exit /b 1
)

echo [2/2] 运行集成测试...
.venv\Scripts\python -m scripts.test_scan_grade_pipeline

echo.
pause
