#!/bin/bash
echo "============================================"
echo "  扫描批卷全链路集成测试 - 运行脚本 (uv)"
echo "============================================"
echo ""

cd "$(dirname "$0")/.."

# 检测 uv 虚拟环境
if [ ! -f ".venv/bin/python" ]; then
    echo "[INFO] 创建 uv 虚拟环境..."
    uv venv
    echo "[INFO] 安装依赖..."
    uv sync
fi

echo "[1/2] 检查 MySQL..."
.venv/bin/python -c "from app.db.database import async_session; import asyncio; asyncio.run(async_session().__aenter__())" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "[FAIL] MySQL 连接失败"
    exit 1
fi

echo "[2/2] 运行集成测试..."
.venv/bin/python -m scripts.test_scan_grade_pipeline
