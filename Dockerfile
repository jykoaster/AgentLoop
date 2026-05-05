# Python 3.11 slim 為基底，再加裝 Node.js 給 claude CLI 使用
FROM python:3.11-slim

# 安裝 Node.js 20 + 必要系統工具
RUN apt-get update && \
    apt-get install -y curl build-essential git && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# 安裝 Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# 安裝 Python 依賴（先複製 requirements 利用 layer cache）
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 建立非 root 使用者（claude --dangerously-skip-permissions 禁止在 root 下執行）
RUN useradd -m -s /bin/bash agent

USER agent
WORKDIR /repo

# 讓 Python 能 import agents 模組
ENV PYTHONPATH=/repo

# 保持容器存活，讓使用者用 docker exec 進入下指令
CMD ["tail", "-f", "/dev/null"]
