"""Command-line entry point for the Task API."""

from __future__ import annotations

import argparse
import logging

from tinyhttp import Server, ServerConfig

from .app import build_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the educational Task API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--database", default="tasks.db")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--no-keep-alive", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    app = build_app(args.database)
    server = Server(
        app,
        ServerConfig(
            host=args.host,
            port=args.port,
            workers=args.workers,
            keep_alive=not args.no_keep_alive,
        ),
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.getLogger("task_api").info("Stopping after keyboard interrupt")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()

