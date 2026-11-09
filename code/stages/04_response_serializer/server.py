"""Stage 4: represent and serialize responses rather than joining ad hoc bytes."""

from __future__ import annotations

import socket
from dataclasses import dataclass, field
from http import HTTPStatus


HOST = "127.0.0.1"
PORT = 8080


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


def serialize(response: Response, *, head_request: bool = False) -> bytes:
    reason = HTTPStatus(response.status).phrase
    headers = dict(response.headers)
    headers.setdefault("Content-Type", "text/plain; charset=utf-8")
    headers["Content-Length"] = str(len(response.body))
    headers["Connection"] = "close"
    start = f"HTTP/1.1 {response.status} {reason}\r\n".encode("ascii")
    fields = b"".join(
        f"{name}: {value}\r\n".encode("iso-8859-1")
        for name, value in headers.items()
    )
    body = b"" if head_request else response.body
    return start + fields + b"\r\n" + body


def parse_request_line(data: bytes) -> tuple[str, str]:
    line = data.split(b"\r\n", 1)[0]
    method, target, version = line.decode("ascii").split(" ")
    if version != "HTTP/1.1":
        raise ValueError("unsupported HTTP version")
    return method, target


def main() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        listener.listen()
        print(f"Listening on http://{HOST}:{PORT}")
        while True:
            connection, _ = listener.accept()
            with connection:
                request_data = connection.recv(32 * 1024)
                try:
                    method, target = parse_request_line(request_data)
                    answer = Response(body=f"You requested {target}\n".encode())
                except (UnicodeError, ValueError):
                    method = "GET"
                    answer = Response(status=400, body=b"Bad request\n")
                connection.sendall(serialize(answer, head_request=method == "HEAD"))


if __name__ == "__main__":
    main()

