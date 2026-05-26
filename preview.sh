#!/bin/bash
# RoboArxiv 本地预览脚本 (现代版)
# 使用 uv 自动处理 Python + 依赖，无需手动安装任何东西

set -e

echo "🚀 正在使用 uv 运行 RoboArxiv 构建脚本..."
echo "   (首次运行会自动下载 Python 依赖，包括 arxiv 官方客户端)"

uv run scripts/build.py

echo ""
echo "✅ 生成完成！"
echo "------------------------------------------------"
echo "请在浏览器中打开: $(pwd)/target/index.html"
echo "------------------------------------------------"
