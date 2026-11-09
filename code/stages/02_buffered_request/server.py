"""Stage 2: buffer a complete header section across arbitrary recv calls."""

from __future__ import annotations

import socket


HOST = "127.0.0.1"
PORT = 8080
MAX_HEADER_BYTES = 32 * 1024


def receive_header(connection: socket.socket) -> bytes:
    buffer = bytearray()
    while b"\r\n\r\n" not in buffer:
        chunk = connection.recv(4096)
        if not chunk:
            raise ValueError("client closed before the header was complete")
        buffer.extend(chunk)
        if len(buffer) > MAX_HEADER_BYTES:
            raise ValueError("header section is too large")
    marker = buffer.index(b"\r\n\r\n") + 4
    return bytes(buffer[:marker])


def make_response(status: int, reason: str, body: bytes) -> bytes:
    return (
        f"HTTP/1.1 {status} {reason}\r\n".encode("ascii")
        + b"Content-Type: text/plain; charset=utf-8\r\n"
        + f"Content-Length: {len(body)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n"
        + body
    )


def main() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        listener.listen()
        print(f"Listening on http://{HOST}:{PORT}")
        while True:
            connection, address = listener.accept()
            with connection:
                try:
                    header = receive_header(connection)
                    print(address, repr(header))
                    response = make_response(200, "OK", b"Header received\n")
                except ValueError as error:
                    response = make_response(400, "Bad Request", str(error).encode())
                connection.sendall(response)


if __name__ == "__main__":
    main()

