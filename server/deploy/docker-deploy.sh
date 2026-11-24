#!/bin/bash
# ============================================================
# E-Learning Docker 部署脚本（备选方案）
# 适用: 不想用宝塔面板，直接用 Docker 部署全部服务
# 前提: 服务器已安装 Docker 和 Docker Compose
# ============================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()   { echo -e "${GREEN}[OK]${NC}    $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "=============================================="
echo "  E-Learning Docker 部署方案"
echo "=============================================="
echo ""

# 检查 Docker
if ! command -v docker &>/dev/null; then
    err "Docker 未安装！请先安装 Docker"
    exit 1
fi
if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
    err "Docker Compose 未安装！"
    exit 1
fi

DOCKER_COMPOSE="docker-compose"
if docker compose version &>/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
fi

# 1. 构建前端
log "构建前端..."
cd "$PROJECT_DIR/client"
npm install --silent
npm run build
npm --prefix h5 run build
ok "前端构建完成"

# 2. 构建后端 Docker 镜像
log "构建后端 Docker 镜像..."
cd "$PROJECT_DIR"

# 3. 构建并启动主应用
docker build -t elearning-backend:latest -f server/deploy/Dockerfile .
ok "后端镜像构建完成"

# 4. 在同一个 Compose 项目启动应用和基础设施，沿用旧项目名以保留数据卷
COMPOSE_FILES=(--env-file server/.env -p backend -f server/deploy/docker-compose.yml -f server/deploy/docker-compose.app.yml)
$DOCKER_COMPOSE "${COMPOSE_FILES[@]}" up -d
ok "后端服务已启动"

# 5. Nginx 配置提示
echo ""
echo "=============================================="
echo "  Docker 部署完成！"
echo "=============================================="
echo ""
echo "  后端 API:      http://服务器IP:8000"
echo "  Attu 管理界面: http://服务器IP:18000"
echo ""
echo "  请配置 Nginx 将域名反向代理到 :8000"
echo "  Nginx 模板参见: server/deploy/nginx.conf.example"
echo ""
echo "  管理命令:"
echo "    docker ps                    # 查看所有容器"
echo "    docker logs elearning-app    # 查看后端日志"
echo "    $DOCKER_COMPOSE ${COMPOSE_FILES[*]} stop elearning  # 停止应用"
echo "=============================================="
