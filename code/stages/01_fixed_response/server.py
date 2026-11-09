"""Stage 1: send one fixed HTTP response, then stop."""

from __future__ import annotations

import socket


HOST = "127.0.0.1"
PORT = 8080
BODY = b"Hello from a raw Python socket!\n"


def response_bytes() -> bytes:
    return (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: text/plain; charset=utf-8\r\n"
        + f"Content-Length: {len(BODY)}\r\n".encode("ascii")
        + b"Connection: close\r\n\r\n"
        + BODY
    )


def main() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        listener.listen(1)
        print(f"Open http://{HOST}:{PORT}")
        connection, address = listener.accept()
        with connection:
            print("client:", address)
            connection.recv(4096)
            connection.sendall(response_bytes())


if __name__ == "__main__":
    main()

