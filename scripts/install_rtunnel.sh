#!/usr/bin/env bash
set -euo pipefail

target="${1:-}"
RTUNNEL_URL="${RTUNNEL_URL:-https://github.com/Sarfflow/rtunnel/releases/download/v1.0.0/rtunnel-linux}"

if [[ -z "$target" ]]; then
  echo "usage: scripts/install_rtunnel.sh /path/to/rtunnel" >&2
  exit 2
fi

if [[ -x "$target" ]]; then
  echo "rtunnel already exists: $target"
  exit 0
fi

mkdir -p "$(dirname "$target")"
echo "downloading rtunnel to $target"
curl -L "$RTUNNEL_URL" -o "$target"
chmod +x "$target"
