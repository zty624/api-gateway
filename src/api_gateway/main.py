from __future__ import annotations

import argparse
import logging
import os

import uvicorn

from .app import create_app
from .config import load_config


def build_app() -> None:
    parser = argparse.ArgumentParser(description="rtunnel tmux gateway")
    parser.add_argument(
        "--config",
        default=os.environ.get("GATEWAY_CONFIG", "config.yaml"),
        help="网关配置文件路径，默认读取 GATEWAY_CONFIG 或 config.yaml",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    app = create_app(config)

    uvicorn.run(
        app,
        host=config.listen.host,
        port=config.listen.port,
        log_level="info",
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_app()


if __name__ == "__main__":
    main()
