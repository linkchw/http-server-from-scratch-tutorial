from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(stage: str):
    path = ROOT / stage / "server.py"
    spec = importlib.util.spec_from_file_location(stage, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[stage] = module
    spec.loader.exec_module(module)
    return module


class SnapshotTests(unittest.TestCase):
    def test_stage_1_response_is_framed(self) -> None:
        module = load("01_fixed_response")
        data = module.response_bytes()
        self.assertTrue(data.startswith(b"HTTP/1.1 200 OK\r\n"))
        self.assertTrue(data.endswith(module.BODY))
        self.assertIn(f"Content-Length: {len(module.BODY)}".encode(), data)

    def test_stage_3_parses_request_head(self) -> None:
        module = load("03_request_parser")
        method, target, version, headers = module.parse_head(
            b"POST /tasks HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2"
        )
        self.assertEqual((method, target, version), ("POST", "/tasks", "HTTP/1.1"))
        self.assertEqual(headers["content-length"], "2")

    def test_stage_4_head_response_keeps_length(self) -> None:
        module = load("04_response_serializer")
        data = module.serialize(module.Response(body=b"hello"), head_request=True)
        self.assertIn(b"Content-Length: 5", data)
        self.assertTrue(data.endswith(b"\r\n\r\n"))

    def test_stage_5_routes_parameters(self) -> None:
        module = load("05_router")
        response = module.handle(b"GET /tasks/42 HTTP/1.1\r\nHost: test\r\n\r\n")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b"Task 42\n")

    def test_stage_6_returns_json(self) -> None:
        module = load("06_json_middleware")
        response = module.handle(b"GET /health HTTP/1.1\r\nHost: test\r\n\r\n")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.body, b'{"status":"ok"}')

    def test_stage_7_response_is_bounded_example(self) -> None:
        module = load("07_bounded_concurrency")
        data = module.response(503, {"title": "busy"})
        self.assertIn(b"503 Service Unavailable", data)


if __name__ == "__main__":
    unittest.main()
