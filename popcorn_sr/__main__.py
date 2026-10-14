import argparse
import asyncio
import os
import signal
from pathlib import Path

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Popcorn SR — pair your library with your processing power.")
    subs = parser.add_subparsers(dest="mode", required=True)
    serve = subs.add_parser("serve", help="Run the lightweight library manager and web interface.")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8787)
    worker = subs.add_parser("worker", help="Run a paired processing worker.")
    worker.add_argument("--manager", default=os.environ.get("POPCORN_MANAGER", "http://manager:8787"))
    worker.add_argument("--state", type=Path, default=Path(os.environ.get("POPCORN_WORKER_STATE", "/state")))
    worker.add_argument("--scratch", type=Path, default=Path(os.environ.get("POPCORN_SCRATCH", "/scratch")))
    worker.add_argument("--name", default=os.environ.get("POPCORN_WORKER_NAME"))
    initialize = subs.add_parser("init-scratch", help="Mark an existing mounted scratch directory as ready.")
    initialize.add_argument("path", type=Path)
    login = subs.add_parser("set-login", help="Set the owner login without changing workers or media.")
    login.add_argument("--username", required=True)
    login.add_argument("--password-stdin", action="store_true")
    subs.add_parser("request-update", help="Ask the configured host service to update this worker when idle.")
    args = parser.parse_args()
    if args.mode == "serve":
        from .server import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False)
    elif args.mode == "worker":
        from .worker import Worker

        async def run_worker():
            task = asyncio.current_task()
            if os.name == "posix":
                asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
            try:
                await Worker(args.manager, args.state, args.scratch, args.name).run(
                    os.environ.get("POPCORN_PAIR_CODE")
                )
            except asyncio.CancelledError:
                print("Worker stopped; active processing terminated and scratch cleanup checked.", flush=True)

        try:
            asyncio.run(run_worker())
        except (ValueError, OSError) as exc:
            parser.exit(1, f"Worker stopped: {exc}\n")
    elif args.mode == "init-scratch":
        from .scratch import initialize

        try:
            initialize(args.path)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(f"Scratch ready: {args.path.resolve()}")
    elif args.mode == "request-update":
        from .updates import WorkerUpdates

        try:
            WorkerUpdates().request()
        except (ValueError, OSError) as exc:
            parser.exit(1, f"Update not requested: {exc}\n")
        print("Update requested. The host service waits for the current job before replacing the container.")
    elif args.mode == "set-login":
        import getpass
        import sys

        from .auth import Authentication
        from .db import Store

        password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("New password: ")
        try:
            Authentication(Store(Path(os.environ.get("POPCORN_STATE", "/state")))).provision(args.username, password)
        except (ValueError, OSError) as exc:
            parser.exit(1, f"Login not changed: {exc}\n")
        print("Owner login configured. Worker pairing and media are unchanged.")


if __name__ == "__main__":
    main()
