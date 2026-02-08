from __future__ import annotations

import argparse

import uvicorn

from .config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["debug", "prod"], default="debug")
    args = parser.parse_args()

    settings = get_settings()
    reload_enabled = args.mode == "debug"
    uvicorn.run(
        "deepagent.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=reload_enabled,
    )


if __name__ == "__main__":
    main()

