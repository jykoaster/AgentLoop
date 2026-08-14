# Python 3.11 slim 為基底，再加裝 Node.js 給 claude CLI 使用
FROM python:3.11-slim

# 安裝 Node.js 20 + 必要系統工具
RUN apt-get update && \
    apt-get install -y curl build-essential git sudo && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# 安裝 Docker CLI（容器內不跑 daemon，透過掛載進來的 host docker.sock 操控宿主的
# docker engine，讓 agent 能在容器內對「目標專案」執行 docker compose up / exec 等指令）
RUN install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
      > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y docker-ce-cli docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

# 安裝 Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# 安裝 OpenSpec CLI（analyze_plan 產出的規格文件遵照其 change/spec delta 規則，
# review 通過後由 archive 節點呼叫 `openspec archive` 合併進目標專案的 openspec/specs/）
RUN npm install -g @fission-ai/openspec

# 安裝 Python 依賴（先複製 requirements 利用 layer cache）
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 建立非 root 使用者（claude --dangerously-skip-permissions 禁止在 root 下執行）
RUN useradd -m -s /bin/bash agent

# 預先建立 .claude/skills（讓 docker-compose.yml 掛載 host 的 skills 內容時，父目錄
# 已是 agent 所有；.claude 底下其餘檔案——登入憑證、session 快取——由容器自己的
# named volume 持有，不與 host 共用，見 docker-compose.yml 說明）
RUN mkdir -p /home/agent/.claude/skills && chown -R agent:agent /home/agent/.claude

# host 掛載進來的 docker.sock 擁有者/群組是宿主環境決定的（在 Docker Desktop 上常見非 root
# 無法單靠 group 權限連線），因此讓 agent 可免密碼、僅限 docker 指令以 root 執行
RUN echo "agent ALL=(root) NOPASSWD: /usr/bin/docker" > /etc/sudoers.d/agent-docker && \
    chmod 0440 /etc/sudoers.d/agent-docker

USER agent
WORKDIR /repo

# 讓 Python 能 import agents 模組
ENV PYTHONPATH=/repo

# 保持容器存活，讓使用者用 docker exec 進入下指令
CMD ["tail", "-f", "/dev/null"]
