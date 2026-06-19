FROM python:3.13-slim

ARG RTUNNEL_URL=https://github.com/Sarfflow/rtunnel/releases/download/v1.0.0/rtunnel-linux

WORKDIR /app

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        nginx \
        openssh-server \
        tmux \
    && rm -rf /var/lib/apt/lists/*

RUN curl -L "$RTUNNEL_URL" -o /usr/local/bin/rtunnel \
    && chmod +x /usr/local/bin/rtunnel

COPY pyproject.toml README.md config.example.yaml ./
COPY deploy ./deploy
COPY scripts ./scripts
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

EXPOSE 8080

ENV GATEWAY_CONFIG=/app/config.yaml
ENV PUBLIC_PORT=8080
ENV RTUNNEL_BINARY=/usr/local/bin/rtunnel

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
