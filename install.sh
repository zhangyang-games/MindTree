#!/bin/bash

# ─────────────────────────────────────────
#  MindTree 一键安装脚本
#  项目地址: github.com/zhangyang-games/MindTree
# ─────────────────────────────────────────

set -e

REPO="https://raw.githubusercontent.com/zhangyang-games/MindTree/main"
INSTALL_DIR="$HOME/mindtree"
SERVICE_NAME="mindtree"
PORT=8849
PYTHON=$(command -v python3 || command -v python)

echo ""
echo "╔══════════════════════════════════════╗"
echo "║        MindTree 安装程序             ║"
echo "╚══════════════════════════════════════╝"
echo ""

# ── 1. 创建目录 ──
echo "▶ 创建安装目录 $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"

# ── 2. 下载文件 ──
echo "▶ 从 GitHub 下载文件..."
curl -fsSL "$REPO/server.py"   -o "$INSTALL_DIR/server.py"
curl -fsSL "$REPO/index.html"  -o "$INSTALL_DIR/index.html"
echo "  ✓ server.py"
echo "  ✓ index.html"

# ── 3. 确保 pip 可用 ──
echo "▶ 检查 pip 是否可用..."
if ! $PYTHON -m pip --version &>/dev/null; then
    echo "  pip 未安装，正在通过 apt 安装 python3-pip..."
    apt-get update -qq
    apt-get install -y python3-pip -qq
    echo "  ✓ python3-pip 安装完成"
else
    echo "  ✓ pip 已可用"
fi

# ── 4. 安装 Python 依赖 ──
echo "▶ 安装 Python 依赖 (fastapi, uvicorn)..."
if $PYTHON -m pip install fastapi uvicorn --quiet --break-system-packages 2>/dev/null; then
    echo "  ✓ 依赖安装完成"
elif $PYTHON -m pip install fastapi uvicorn --quiet 2>/dev/null; then
    echo "  ✓ 依赖安装完成"
else
    echo "  ✗ 依赖安装失败，请查看错误信息"
    $PYTHON -m pip install fastapi uvicorn
    exit 1
fi

# ── 检测当前用户 ──
CURRENT_USER=$(whoami)
PYTHON_PATH=$(command -v python3 || command -v python)

# ── 5. 创建 systemd 服务 ──
echo "▶ 创建系统服务 $SERVICE_NAME ..."

tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=MindTree - 私人思维导图
After=network.target

[Service]
User=${CURRENT_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${PYTHON_PATH} ${INSTALL_DIR}/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "  ✓ 服务文件已创建"

# ── 6. 启动服务 ──
echo "▶ 启动 MindTree 服务..."
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" --quiet
systemctl restart "$SERVICE_NAME"

sleep 2

# ── 7. 检查状态 ──
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "  ✓ 服务运行正常"
else
    echo "  ✗ 服务启动失败，查看日志："
    echo "    sudo journalctl -u $SERVICE_NAME -n 30"
    exit 1
fi

# ── 8. 完成 ──
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "╔══════════════════════════════════════╗"
echo "║          安装成功 🎉                 ║"
echo "╚══════════════════════════════════════╝"
echo ""
echo "  访问地址:  http://${LOCAL_IP}:${PORT}"
echo "  安装目录:  ${INSTALL_DIR}"
echo "  数据库:    ${INSTALL_DIR}/mindtree.db"
echo ""
echo "  常用命令:"
echo "    查看状态   systemctl status $SERVICE_NAME"
echo "    重启服务   systemctl restart $SERVICE_NAME"
echo "    查看日志   journalctl -u $SERVICE_NAME -f"
echo "    停止服务   systemctl stop $SERVICE_NAME"
echo ""
echo "  更新到最新版本:"
echo "    curl -fsSL $REPO/install.sh | bash"
echo ""
