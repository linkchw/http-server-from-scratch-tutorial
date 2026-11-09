"""Stage 7: add a fixed worker pool and finite connection queue."""

from __future__ import annotations

import json
import queue
import socket
import threading
from http import HTTPStatus


HOST = "127.0.0.1"
PORT = 8080
WORKERS = 4
QUEUE_SIZE = 16
connections: queue.Queue[tuple[socket.socket, tuple[str, int]] | None] = queue.Queue(QUEUE_SIZE)


def response(status: int, document: dict) -> bytes:
    body = json.dumps(document, separators=(",", ":")).encode()
    return (
        f"HTTP/1.1 {status} {HTTPStatus(status).phrase}\r\n"
        "Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n".encode()
        + body
    )


def worker() -> None:
    while True:
        item = connections.get()
        if item is None:
            connections.task_done()
            return
        connection, address = item
        try:
            with connection:
                connection.settimeout(5)
                data = connection.recv(32 * 1024)
                if data.startswith(b"GET /health HTTP/1.1\r\n"):
                    result = response(200, {"status": "ok", "worker": threading.current_thread().name})
                else:
                    result = response(404, {"title": "Not Found", "status": 404})
                connection.sendall(result)
                print(address, len(data), "bytes")
        finally:
            connections.task_done()


def main() -> None:
    for number in range(WORKERS):
        threading.Thread(target=worker, name=f"worker-{number + 1}", daemon=True).start()
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        listener.listen(128)
        print(f"Listening on http://{HOST}:{PORT} with {WORKERS} workers")
        while True:
            connection, address = listener.accept()
            try:
                connections.put_nowait((connection, address))
            except queue.Full:
                with connection:
                    connection.sendall(response(503, {"title": "Server Busy", "status": 503}))


if __name__ == "__main__":
    main()

