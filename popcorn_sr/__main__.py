import argparse
import asyncio
import os
import secrets
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
    subs.add_parser("access-key", help="Generate a random manager access key.")
    args = parser.parse_args()
    if args.mode == "serve":
        from .server import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port, access_log=False)
    elif args.mode == "worker":
        from .worker import Worker

        try:
            asyncio.run(
                Worker(args.manager, args.state, args.scratch, args.name).run(
                    os.environ.get("POPCORN_PAIR_CODE")
                )
            )
        except (ValueError, OSError) as exc:
            parser.exit(1, f"Worker stopped: {exc}\n")
    elif args.mode == "init-scratch":
        if not args.path.is_dir():
            parser.error("Scratch folder must already exist. Mount the intended drive first.")
        marker = args.path / ".popcorn-scratch"
        if not marker.exists():
            marker.write_text(secrets.token_hex(16) + "\n")
        print(f"Scratch ready: {args.path.resolve()}")
    else:
        print(secrets.token_urlsafe(32))


if __name__ == "__main__":
    main()
