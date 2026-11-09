"""Stage 5: route structured requests by method and segment pattern."""

from __future__ import annotations

import socket
from dataclasses import dataclass
from http import HTTPStatus
from typing import Callable
from urllib.parse import urlsplit


HOST = "127.0.0.1"
PORT = 8080


@dataclass
class Request:
    method: str
    path: str
    params: dict[str, str]


@dataclass
class Response:
    status: int
    body: bytes


Handler = Callable[[Request], Response]
ROUTES: list[tuple[str, tuple[str, ...], Handler]] = []


def route(method: str, pattern: str):
    def register(handler: Handler) -> Handler:
        ROUTES.append((method, tuple(segment for segment in pattern.split("/") if segment), handler))
        return handler
    return register


def resolve(method: str, path: str) -> tuple[Handler | None, dict[str, str]]:
    actual = tuple(segment for segment in path.split("/") if segment)
    for expected_method, pattern, handler in ROUTES:
        if method != expected_method or len(actual) != len(pattern):
            continue
        params: dict[str, str] = {}
        for expected, value in zip(pattern, actual, strict=True):
            if expected.startswith("{"):
                params[expected[1:-1]] = value
            elif expected != value:
                break
        else:
            return handler, params
    return None, {}


@route("GET", "/hello")
def hello(request: Request) -> Response:
    return Response(200, b"Hello, router!\n")


@route("GET", "/tasks/{task_id}")
def task(request: Request) -> Response:
    return Response(200, f"Task {request.params['task_id']}\n".encode())


def handle(data: bytes) -> Response:
    try:
        request_line = data.split(b"\r\n", 1)[0].decode("ascii")
        method, target, version = request_line.split(" ")
        if version != "HTTP/1.1":
            return Response(505, b"HTTP version not supported\n")
        path = urlsplit(target).path
        handler, params = resolve(method, path)
        if handler is None:
            return Response(404, b"Not found\n")
        return handler(Request(method, path, params))
    except (UnicodeError, ValueError):
        return Response(400, b"Bad request\n")


def serialize(response: Response) -> bytes:
    reason = HTTPStatus(response.status).phrase
    return (
        f"HTTP/1.1 {response.status} {reason}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(response.body)}\r\n"
        "Connection: close\r\n\r\n".encode()
        + response.body
    )


def main() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        listener.listen()
        print(f"Listening on http://{HOST}:{PORT}")
        while True:
            connection, _ = listener.accept()
            with connection:
                connection.sendall(serialize(handle(connection.recv(32 * 1024))))


if __name__ == "__main__":
    main()

