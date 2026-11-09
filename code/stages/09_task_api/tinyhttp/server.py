"""Bounded threaded HTTP server and response serialization."""

from __future__ import annotations

import logging
import queue
import socket
import threading
import time
from dataclasses import dataclass
from email.utils import formatdate
from http import HTTPStatus

from .application import Application
from .models import HTTPError, Request, Response
from .parser import ParserLimits, RequestParser


@dataclass(slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8080
    workers: int = 16
    queue_size: int = 64
    backlog: int = 128
    read_timeout: float = 5.0
    keep_alive: bool = True
    max_requests_per_connection: int = 100
    request_line_limit: int = 8 * 1024
    header_bytes_limit: int = 32 * 1024
    header_count_limit: int = 100
    body_bytes_limit: int = 1024 * 1024

    def parser_limits(self) -> ParserLimits:
        return ParserLimits(
            request_line=self.request_line_limit,
            header_bytes=self.header_bytes_limit,
            header_count=self.header_count_limit,
            body_bytes=self.body_bytes_limit,
        )


class Server:
    def __init__(self, app: Application, config: ServerConfig | None = None) -> None:
        self.app = app
        self.config = config or ServerConfig()
        self.logger = logging.getLogger("tinyhttp.server")
        self._connections: queue.Queue[
            tuple[socket.socket, tuple[str, int]] | None
        ] = queue.Queue(maxsize=self.config.queue_size)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._listener: socket.socket | None = None
        self._workers: list[threading.Thread] = []
        self.address: tuple[str, int] | None = None

    def serve_forever(self) -> None:
        if self._listener is not None:
            raise RuntimeError("Server is already running")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.config.host, self.config.port))
        listener.listen(self.config.backlog)
        listener.settimeout(0.5)
        self._listener = listener
        bound_host, bound_port = listener.getsockname()[:2]
        self.address = (str(bound_host), int(bound_port))
        self._start_workers()
        self._ready.set()
        self.logger.info("Listening on http://%s:%s", *self.address)
        try:
            while not self._stop.is_set():
                try:
                    connection, address = listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                try:
                    self._connections.put_nowait((connection, address))
                except queue.Full:
                    self._reject_overload(connection)
        finally:
            try:
                listener.close()
            finally:
                self._listener = None
                self._signal_workers()

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        return self._ready.wait(timeout)

    def shutdown(self) -> None:
        self._stop.set()
        listener = self._listener
        if listener is not None:
            try:
                listener.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            listener.close()
        self._signal_workers()
        current = threading.current_thread()
        for worker in self._workers:
            if worker is not current:
                worker.join(timeout=self.config.read_timeout + 1.0)

    def _start_workers(self) -> None:
        for number in range(self.config.workers):
            worker = threading.Thread(
                target=self._worker,
                name=f"tinyhttp-worker-{number + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def _signal_workers(self) -> None:
        for _ in self._workers:
            try:
                self._connections.put_nowait(None)
            except queue.Full:
                break

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._connections.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                self._connections.task_done()
                break
            connection, address = item
            try:
                self._handle_connection(connection, address)
            finally:
                self._connections.task_done()

    def _handle_connection(
        self,
        connection: socket.socket,
        address: tuple[str, int],
    ) -> None:
        parser = RequestParser(self.config.parser_limits())
        connection.settimeout(self.config.read_timeout)
        request_count = 0
        with connection:
            while not self._stop.is_set():
                try:
                    request = self._read_request(connection, parser, address)
                except HTTPError as error:
                    response = Response.problem(
                        error.status,
                        error.detail,
                        code=error.code,
                        title=error.title,
                        errors=error.errors,
                        type_uri=error.type_uri,
                    )
                    self._send_response(connection, None, response, keep_alive=False)
                    return
                except socket.timeout:
                    if parser.has_buffered_data:
                        response = Response.problem(
                            408,
                            "The request was not completed before the timeout.",
                            code="request_timeout",
                        )
                        self._send_response(connection, None, response, keep_alive=False)
                    return
                except OSError:
                    return
                if request is None:
                    return
                request_count += 1
                started = time.monotonic()
                response = self.app.handle(request)
                keep_alive = self._should_keep_alive(request, request_count)
                try:
                    sent = self._send_response(
                        connection,
                        request,
                        response,
                        keep_alive=keep_alive,
                    )
                except OSError:
                    return
                elapsed_ms = (time.monotonic() - started) * 1000
                self.logger.info(
                    '%s "%s %s" %s %s %.1fms',
                    address[0],
                    request.method,
                    request.target,
                    response.status,
                    sent,
                    elapsed_ms,
                )
                if not keep_alive:
                    return

    @staticmethod
    def _read_request(
        connection: socket.socket,
        parser: RequestParser,
        address: tuple[str, int],
    ) -> Request | None:
        while True:
            request = parser.pop_request(address)
            if request is not None:
                return request
            chunk = connection.recv(16 * 1024)
            if not chunk:
                if parser.has_buffered_data:
                    raise HTTPError(
                        400,
                        "The connection closed during an incomplete request.",
                        code="incomplete_request",
                    )
                return None
            parser.feed(chunk)

    def _should_keep_alive(self, request: Request, request_count: int) -> bool:
        connection = (request.headers.get("Connection") or "").casefold()
        return (
            self.config.keep_alive
            and connection != "close"
            and request_count < self.config.max_requests_per_connection
            and not self._stop.is_set()
        )

    @staticmethod
    def _send_response(
        connection: socket.socket,
        request: Request | None,
        response: Response,
        *,
        keep_alive: bool,
    ) -> int:
        try:
            reason = HTTPStatus(response.status).phrase
        except ValueError:
            reason = "Unknown"
        headers = response.headers.copy()
        headers.set("Date", formatdate(usegmt=True))
        headers.set("Server", "tinyhttp/1.0")
        headers.set("Connection", "keep-alive" if keep_alive else "close")
        body = response.body
        no_content = 100 <= response.status < 200 or response.status in {204, 304}
        if no_content:
            body_to_send = b""
            headers.remove("Content-Length")
        else:
            headers.set("Content-Length", str(len(body)))
            body_to_send = b"" if request and request.method == "HEAD" else body
        start = f"HTTP/1.1 {response.status} {reason}\r\n".encode("ascii")
        encoded_headers = b"".join(
            f"{name}: {value}\r\n".encode("iso-8859-1") for name, value in headers
        )
        connection.sendall(start + encoded_headers + b"\r\n" + body_to_send)
        return len(body_to_send)

    @staticmethod
    def _reject_overload(connection: socket.socket) -> None:
        with connection:
            response = Response.problem(
                503,
                "The bounded connection queue is full. Try again later.",
                code="server_overloaded",
            )
            try:
                Server._send_response(connection, None, response, keep_alive=False)
            except OSError:
                pass

