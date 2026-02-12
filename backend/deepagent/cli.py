from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from typing import Any, cast

from deepagent.common.config import resolve_path

PID_PATH = resolve_path("./data/server.pid")


def _write_pid(pid: int) -> None:
    PID_PATH.parent.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(str(pid), encoding="utf-8")


def _read_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    content = PID_PATH.read_text(encoding="utf-8").strip()
    return int(content) if content else None


def start(mode: str, detach: bool) -> None:
    # Points to the new entry point
    cmd = [sys.executable, "-m", "deepagent.api.main", "--mode", mode]
    if not detach:
        subprocess.run(cmd, check=False)
        return

    kwargs: dict[str, object] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **cast(Any, kwargs))
    _write_pid(proc.pid)
    print(f"started pid={proc.pid}")


def stop() -> None:
    pid = _read_pid()
    if not pid:
        print("no pid found")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"stopped pid={pid}")
    except ProcessLookupError:
        print("process not found")
    PID_PATH.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    start_cmd = sub.add_parser("start")
    start_cmd.add_argument("--mode", choices=["debug", "prod"], default="debug")
    start_cmd.add_argument("--detach", action="store_true")
    sub.add_parser("stop")
    args = parser.parse_args()

    if args.command == "start":
        start(args.mode, args.detach)
        return
    if args.command == "stop":
        stop()
        return
    parser.print_help()


if __name__ == "__main__":
    main()
