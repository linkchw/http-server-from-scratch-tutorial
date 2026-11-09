"""Stage 6: JSON responses, errors, handlers, and composable middleware."""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import urlsplit


@dataclass
class Request:
    method: str
    path: str


@dataclass
class Response:
    status: int
    body: bytes
    content_type: str = "application/json; charset=utf-8"

    @classmethod
    def json(cls, value: Any, status: int = 200) -> "Response":
        return cls(status, json.dumps(value, separators=(",", ":")).encode())


Handler = Callable[[Request], Response]
Middleware = Callable[[Request, Handler], Response]


def dispatch(request: Request) -> Response:
    if request.method == "GET" and request.path == "/health":
        return Response.json({"status": "ok"})
    return Response.json(
        {"type": "about:blank", "title": "Not Found", "status": 404},
        status=404,
    )


def timing(request: Request, next_handler: Handler) -> Response:
    started = time.monotonic()
    response = next_handler(request)
    elapsed = (time.monotonic() - started) * 1000
    print(request.method, request.path, response.status, f"{elapsed:.1f}ms")
    return response


def compose(handler: Handler, middleware: list[Middleware]) -> Handler:
    for current in reversed(middleware):
        next_handler = handler
        handler = lambda request, current=current, next_handler=next_handler: current(request, next_handler)
    return handler


def handle(data: bytes) -> Response:
    try:
        line = data.split(b"\r\n", 1)[0].decode("ascii")
        method, target, version = line.split(" ")
        if version != "HTTP/1.1":
            return Response.json({"title": "Version Not Supported", "status": 505}, 505)
        request = Request(method, urlsplit(target).path)
        return compose(dispatch, [timing])(request)
    except (UnicodeError, ValueError):
        return Response.json({"title": "Bad Request", "status": 400}, 400)


def serialize(response: Response) -> bytes:
    return (
        f"HTTP/1.1 {response.status} {HTTPStatus(response.status).phrase}\r\n"
        f"Content-Type: {response.content_type}\r\n"
        f"Content-Length: {len(response.body)}\r\n"
        "Connection: close\r\n\r\n".encode()
        + response.body
    )


def main() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 8080))
        listener.listen()
        print("Listening on http://127.0.0.1:8080")
        while True:
            connection, _ = listener.accept()
            with connection:
                connection.sendall(serialize(handle(connection.recv(32 * 1024))))


if __name__ == "__main__":
    main()

