#!/usr/bin/env bash
set -euo pipefail

PUBLIC_PORT="${PUBLIC_PORT:-8080}"
GATEWAY_CONFIG="${GATEWAY_CONFIG:-/app/config.yaml}"
RTUNNEL_BINARY="${RTUNNEL_BINARY:-/usr/local/bin/rtunnel}"
NGINX_TEMPLATE="${NGINX_TEMPLATE:-/app/deploy/nginx.conf.template}"
NGINX_CONFIG="${NGINX_CONFIG:-/tmp/api-gateway-nginx.conf}"
AUTHORIZED_KEYS_PATH="${AUTHORIZED_KEYS_PATH:-/root/.ssh/authorized_keys}"

PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

trap cleanup EXIT INT TERM

prepare_authorized_keys() {
  mkdir -p "$(dirname "$AUTHORIZED_KEYS_PATH")"
  touch "$AUTHORIZED_KEYS_PATH"

  if [[ -n "${GATEWAY_AUTHORIZED_KEYS:-}" ]]; then
    printf "%s\n" "$GATEWAY_AUTHORIZED_KEYS" >"$AUTHORIZED_KEYS_PATH"
  elif [[ -f /app/authorized_keys ]]; then
    cp /app/authorized_keys "$AUTHORIZED_KEYS_PATH"
  fi

  chmod 700 "$(dirname "$AUTHORIZED_KEYS_PATH")"
  chmod 600 "$AUTHORIZED_KEYS_PATH"
}

start_sshd() {
  mkdir -p /run/sshd
  ssh-keygen -A
  /usr/sbin/sshd \
    -D \
    -p 2222 \
    -o PermitRootLogin=prohibit-password \
    -o PasswordAuthentication=no &
  PIDS+=("$!")
}

start_rtunnel() {
  "$RTUNNEL_BINARY" 127.0.0.1:2222 127.0.0.1:10022 &
  PIDS+=("$!")
}

start_api() {
  python -m api_gateway --config "$GATEWAY_CONFIG" &
  PIDS+=("$!")
}

start_nginx() {
  sed "s/\${PUBLIC_PORT}/${PUBLIC_PORT}/g" "$NGINX_TEMPLATE" >"$NGINX_CONFIG"
  nginx -c "$NGINX_CONFIG" -g "daemon off;" &
  PIDS+=("$!")
}

prepare_authorized_keys
start_sshd
start_rtunnel
start_api
start_nginx

wait -n "${PIDS[@]}"
