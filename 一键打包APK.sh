#!/usr/bin/env bash
# =============================================================================
# 包租婆出租屋管家 · 安卓版 —— 一键打包脚本（Linux / WSL2 下执行）
# 用法：  bash 一键打包APK.sh
# 产物：  bin/baozupo-2.1.0-*.apk
# =============================================================================
set -e
cd "$(dirname "$0")"

echo "==> 1/4 安装系统依赖（需要 sudo）"
sudo apt-get update -qq
sudo apt-get install -y -qq git zip unzip openjdk-17-jdk python3-pip autoconf libtool \
    pkg-config zlib1g-dev libncurses5-dev libncursesw5-dev cmake libffi-dev libssl-dev

echo "==> 2/4 安装 buildozer"
python3 -m pip install --upgrade pip
python3 -m pip install buildozer "cython==0.29.36"

echo "==> 3/4 检查中文字体"
if [ ! -f fonts/simhei.ttf ]; then
    echo "[!] 缺少 fonts/simhei.ttf，请从 Windows 的 C:\\Windows\\Fonts\\ 复制一个中文字体过来"
    exit 1
fi

echo "==> 4/4 开始打包（第一次约 40 分钟，请耐心等待）"
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
yes | buildozer -v android debug

echo
echo "=========================================="
echo " 打包完成！APK 在 bin/ 目录里："
ls -lh bin/*.apk
echo "=========================================="
