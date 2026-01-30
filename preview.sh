#!/bin/bash

# RoboArxiv 本地预览生成脚本

# 1. 检查依赖项
if ! command -v jq &> /dev/null; then
    echo "错误: 未找到 'jq'。请先安装它 (例如: sudo apt install jq)。"
    exit 1
fi

if ! command -v curl &> /dev/null; then
    echo "错误: 未找到 'curl'。请先安装它。"
    exit 1
fi

# 2. 如果不存在 arxivfeed 工具则下载
if [ ! -f "./arxivfeed" ]; then
    echo "正在下载 arxivfeed 工具..."
    REPO="NotCraft/ArxivFeed"
    VERSION="latest"
    MATCH="arxivfeed-.+-x86_64-unknown-linux-musl.tar.gz$"
    
    ASSET_URL=$(curl -sL -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/repos/${REPO}/releases/${VERSION}" \
        | jq -r ".assets | .[] | select(.name | test(\"${MATCH}\")) | .browser_download_url")

    if [ -z "$ASSET_URL" ] || [ "$ASSET_URL" == "null" ]; then
        echo "错误: 无法获取 arxivfeed 的下载地址。"
        exit 1
    fi

    curl -sL -o arxivfeed.tgz "$ASSET_URL"
    tar -zxvf arxivfeed.tgz --strip-components 1 $(tar tf arxivfeed.tgz | grep /arxivfeed)
    chmod +x arxivfeed
    rm arxivfeed.tgz
    echo "arxivfeed 工具下载完成。"
fi

# 3. 运行工具生成预览
echo "正在生成预览页面..."
./arxivfeed

if [ $? -eq 0 ]; then
    echo "------------------------------------------------"
    echo "生成成功！预览文件已存放在 'target' 目录中。"
    echo "请在浏览器中打开: $(pwd)/target/index.html"
    echo "------------------------------------------------"
else
    echo "错误: 页面生成失败。"
    exit 1
fi
