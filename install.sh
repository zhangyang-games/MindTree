#!/bin/bash

# ─────────────────────────────────────────
#  MindTree Docker 安装脚本
#  项目地址: github.com/zhangyang-games/MindTree
# ─────────────────────────────────────────

set -e

REPO="https://raw.githubusercontent.com/zhangyang-games/MindTree/main"
INSTALL_DIR="$HOME/mindtree"
DATA_DIR="$HOME/mindtree_data"
PORT=8849

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     MindTree Docker 安装程序         ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. 检查 Docker ──
echo "▶ 检查 Docker..."
if ! command -v docker &>/dev/null; then
    echo "  Docker 未安装，正在安装..."
    curl -fsSL https://get.docker.com | sh
    echo "  ✓ Docker 安装完成"
else
    echo "  ✓ Docker 已可用 ($(docker --version | cut -d' ' -f3 | tr -d ','))"
fi

# ── 2. 创建目录 ──
echo "▶ 创建目录..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR"
echo "  ✓ $INSTALL_DIR"
echo "  ✓ $DATA_DIR (数据持久化)"

# ── 3. 下载文件 ──
echo "▶ 从 GitHub 下载文件..."
curl -fsSL "$REPO/server.py"    -o "$INSTALL_DIR/server.py"
curl -fsSL "$REPO/index.html"   -o "$INSTALL_DIR/index.html"
curl -fsSL "$REPO/Dockerfile"   -o "$INSTALL_DIR/Dockerfile"
echo "  ✓ server.py"
echo "  ✓ index.html"
echo "  ✓ Dockerfile"

# ── 4. 写 docker-compose 片段（追加到现有或新建）──
COMPOSE_FILE="$HOME/docker-compose.yml"

echo "▶ 配置 docker-compose..."

if [ -f "$COMPOSE_FILE" ]; then
    # 检查是否已经有 mindtree 服务
    if grep -q "mindtree:" "$COMPOSE_FILE"; then
        echo "  ℹ mindtree 已在 docker-compose.yml 中，跳过追加"
    else
        # 追加到现有 docker-compose.yml
        cat >> "$COMPOSE_FILE" <<EOF

  mindtree:
    build:
      context: ./mindtree
      dockerfile: Dockerfile
    container_name: mindtree
    restart: always
    ports:
      - "${PORT}:8849"
    volumes:
      - ${DATA_DIR}:/app/uploads
      - ${DATA_DIR}:/app/data
    environment:
      - TZ=Asia/Shanghai
EOF
        echo "  ✓ 已追加到现有 $COMPOSE_FILE"
    fi
else
    # 新建 docker-compose.yml
    cat > "$COMPOSE_FILE" <<EOF
version: '3.8'
services:
  mindtree:
    build:
      context: ./mindtree
      dockerfile: Dockerfile
    container_name: mindtree
    restart: always
    ports:
      - "${PORT}:8849"
    volumes:
      - ${DATA_DIR}:/app/uploads
      - ${DATA_DIR}:/app/data
    environment:
      - TZ=Asia/Shanghai
EOF
        echo "  ✓ 新建 $COMPOSE_FILE"
fi

# ── 5. 构建并启动 ──
echo "▶ 构建 Docker 镜像（首次约需 1-2 分钟）..."
cd "$HOME"
docker compose build mindtree
echo "  ✓ 镜像构建完成"

echo "▶ 启动容器..."
docker compose up -d mindtree
sleep 3

# ── 6. 检查状态 ──
if docker ps | grep -q mindtree; then
    echo "  ✓ 容器运行正常"
else
    echo "  ✗ 容器启动失败，查看日志："
    echo "    docker logs mindtree"
    exit 1
fi

# ── 7. 完成 ──
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "╔══════════════════════════════════════╗"
echo "║          安装成功 🎉                 ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  访问地址:  http://${LOCAL_IP}:${PORT}"
echo "  默认账号:  admin"
echo "  默认密码:  mindtree123"
echo "  数据目录:  ${DATA_DIR}"
echo ""
echo "  常用命令:"
echo "    查看状态   docker ps | grep mindtree"
echo "    查看日志   docker logs mindtree -f"
echo "    重启容器   docker compose restart mindtree"
echo "    停止容器   docker compose stop mindtree"
echo ""
echo "  更新到最新版本:"
echo "    curl -fsSL $REPO/install.sh | bash"
echo ""
