FROM python:3.12-slim

# Install Node.js for Claude Code CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gosu && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /opt/assistant

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app/ app/

# Non-root user for Claude Code CLI
RUN useradd -m -s /bin/bash arlo

EXPOSE 8002

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["entrypoint.sh"]
