from __future__ import annotations

import http.client
import json
import socket
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from tinyhttp import Application, Request, Response, Server, ServerConfig


class ServerTests(unittest.TestCase):
    def setUp(self) -> None:
        app = Application()

        @app.route("GET", "/hello")
        def hello(request: Request) -> Response:
            return Response.json({"hello": "world"})

        self.server = Server(
            app,
            ServerConfig(port=0, workers=4, queue_size=8, read_timeout=1.0),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.assertTrue(self.server.wait_until_ready())
        assert self.server.address is not None
        self.host, self.port = self.server.address

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)

    def test_standard_library_client_and_keep_alive(self) -> None:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=2)
        connection.request("GET", "/hello")
        first = connection.getresponse()
        self.assertEqual(first.status, 200)
        self.assertEqual(json.loads(first.read()), {"hello": "world"})
        connection.request("HEAD", "/hello")
        second = connection.getresponse()
        self.assertEqual(second.status, 200)
        self.assertEqual(second.read(), b"")
        self.assertGreater(int(second.getheader("Content-Length")), 0)
        connection.close()

    def test_raw_malformed_request_gets_problem_response(self) -> None:
        with socket.create_connection((self.host, self.port), timeout=2) as client:
            client.sendall(b"GET /hello HTTP/1.1\r\n\r\n")
            received = receive_until_close(client)
        self.assertIn(b"400 Bad Request", received)
        self.assertIn(b"application/problem+json", received)

    def test_fragmented_network_request(self) -> None:
        with socket.create_connection((self.host, self.port), timeout=2) as client:
            for part in (
                b"GET /hel",
                b"lo HTTP/1.1\r\nHo",
                b"st: localhost\r\nConnection: close\r\n\r\n",
            ):
                client.sendall(part)
            received = receive_until_close(client)
        self.assertIn(b"200 OK", received)
        self.assertIn(b'{"hello":"world"}', received)

    def test_fifty_concurrent_clients_complete(self) -> None:
        def fetch(_: int) -> int:
            connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
            connection.request("GET", "/hello", headers={"Connection": "close"})
            response = connection.getresponse()
            response.read()
            connection.close()
            return response.status

        with ThreadPoolExecutor(max_workers=50) as pool:
            statuses = list(pool.map(fetch, range(50)))
        self.assertEqual(statuses, [200] * 50)


def receive_until_close(client: socket.socket) -> bytes:
    parts: list[bytes] = []
    while True:
        chunk = client.recv(4096)
        if not chunk:
            return b"".join(parts)
        parts.append(chunk)


if __name__ == "__main__":
    unittest.main()
