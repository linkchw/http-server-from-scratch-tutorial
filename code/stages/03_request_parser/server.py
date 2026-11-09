"""Stage 3: parse method, target, version, fields, and a length-framed body."""

from __future__ import annotations

import socket
from dataclasses import dataclass


HOST = "127.0.0.1"
PORT = 8080


@dataclass
class Request:
    method: str
    target: str
    version: str
    headers: dict[str, str]
    body: bytes


def parse_head(head: bytes) -> tuple[str, str, str, dict[str, str]]:
    lines = head.split(b"\r\n")
    try:
        method_raw, target_raw, version_raw = lines[0].split(b" ")
    except ValueError as error:
        raise ValueError("malformed request line") from error
    method = method_raw.decode("ascii")
    target = target_raw.decode("ascii")
    version = version_raw.decode("ascii")
    if version != "HTTP/1.1":
        raise ValueError("only HTTP/1.1 is supported")
    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, separator, value = line.partition(b":")
        if not separator:
            raise ValueError("malformed header")
        key = name.decode("ascii").casefold()
        if key in headers:
            raise ValueError("duplicate header")
        headers[key] = value.decode("iso-8859-1").strip()
    if not headers.get("host"):
        raise ValueError("Host is required")
    return method, target, version, headers


def receive_request(connection: socket.socket) -> Request:
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        chunk = connection.recv(4096)
        if not chunk:
            raise ValueError("incomplete header")
        buffer.extend(chunk)
        if len(buffer) > 32 * 1024:
            raise ValueError("header too large")
    marker = buffer.index(b"\r\n\r\n")
    method, target, version, headers = parse_head(bytes(buffer[:marker]))
    raw_length = headers.get("content-length", "0")
    if not raw_length.isdecimal():
        raise ValueError("invalid Content-Length")
    length = int(raw_length)
    if length > 1024 * 1024:
        raise ValueError("body too large")
    body_start = marker + 4
    while len(buffer) - body_start < length:
        chunk = connection.recv(4096)
        if not chunk:
            raise ValueError("incomplete body")
        buffer.extend(chunk)
    return Request(method, target, version, headers, bytes(buffer[body_start:body_start + length]))


def response(body: bytes, status: str = "200 OK") -> bytes:
    return (
        f"HTTP/1.1 {status}\r\nContent-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
        + body
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
                try:
                    request = receive_request(connection)
                    body = f"{request.method} {request.target}\n".encode()
                    connection.sendall(response(body))
                except ValueError as error:
                    connection.sendall(response(str(error).encode(), "400 Bad Request"))


if __name__ == "__main__":
    main()

