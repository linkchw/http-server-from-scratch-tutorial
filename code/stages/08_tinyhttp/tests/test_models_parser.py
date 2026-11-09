from __future__ import annotations

import json
import unittest

from tinyhttp import Headers, HTTPError, Request, Response
from tinyhttp.parser import ParserLimits, RequestParser


class HeadersTests(unittest.TestCase):
    def test_case_insensitive_multi_value_access(self) -> None:
        headers = Headers([("X-Trace", "one"), ("x-trace", "two")])
        self.assertEqual(headers.get("X-TRACE"), "two")
        self.assertEqual(headers.get_all("x-trace"), ["one", "two"])
        headers.set("X-Trace", "three")
        self.assertEqual(headers.get_all("x-trace"), ["three"])

    def test_json_response_is_utf8(self) -> None:
        response = Response.json({"message": "café"})
        self.assertEqual(json.loads(response.body), {"message": "café"})
        self.assertIn("application/json", response.headers.get("content-type") or "")

    def test_rejects_response_splitting_characters(self) -> None:
        with self.assertRaises(ValueError):
            Headers({"X-Unsafe": "value\r\nX-Injected: yes"})


class ParserTests(unittest.TestCase):
    def test_fragmented_request_and_leftover_request(self) -> None:
        first = (
            b"POST /tasks?tag=a&tag=b HTTP/1.1\r\n"
            b"Host: localhost\r\nContent-Length: 2\r\n\r\n{}"
        )
        second = b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n"
        parser = RequestParser()
        data = first + second
        for byte in data:
            parser.feed(bytes([byte]))
            request = parser.pop_request(("127.0.0.1", 1234))
            if byte < 0:  # pragma: no cover - keeps the loop shape explicit
                self.fail("unreachable")
            if request is not None:
                break
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.path, "/tasks")
        self.assertEqual(request.query, {"tag": ["a", "b"]})
        self.assertEqual(request.body, b"{}")
        remaining_start = len(first)
        parser.feed(data[remaining_start:])
        following = parser.pop_request()
        self.assertIsNotNone(following)
        assert following is not None
        self.assertEqual(following.path, "/health")

    def test_two_requests_from_one_feed(self) -> None:
        parser = RequestParser()
        parser.feed(
            b"GET /a HTTP/1.1\r\nHost: test\r\n\r\n"
            b"GET /b HTTP/1.1\r\nHost: test\r\n\r\n"
        )
        self.assertEqual(parser.pop_request().path, "/a")  # type: ignore[union-attr]
        self.assertEqual(parser.pop_request().path, "/b")  # type: ignore[union-attr]

    def test_rejects_duplicate_content_length(self) -> None:
        parser = RequestParser()
        parser.feed(
            b"POST / HTTP/1.1\r\nHost: test\r\n"
            b"Content-Length: 1\r\nContent-Length: 1\r\n\r\nx"
        )
        with self.assertRaisesRegex(HTTPError, "Duplicate") as context:
            parser.pop_request()
        self.assertEqual(context.exception.status, 400)

    def test_rejects_transfer_encoding(self) -> None:
        parser = RequestParser()
        parser.feed(
            b"POST / HTTP/1.1\r\nHost: test\r\n"
            b"Transfer-Encoding: chunked\r\n\r\n"
        )
        with self.assertRaises(HTTPError) as context:
            parser.pop_request()
        self.assertEqual(context.exception.status, 501)

    def test_requires_exactly_one_host(self) -> None:
        parser = RequestParser()
        parser.feed(b"GET / HTTP/1.1\r\n\r\n")
        with self.assertRaises(HTTPError) as context:
            parser.pop_request()
        self.assertEqual(context.exception.code, "invalid_host")

    def test_enforces_body_limit_before_waiting_for_body(self) -> None:
        parser = RequestParser(ParserLimits(body_bytes=3))
        parser.feed(
            b"POST / HTTP/1.1\r\nHost: test\r\nContent-Length: 4\r\n\r\n"
        )
        with self.assertRaises(HTTPError) as context:
            parser.pop_request()
        self.assertEqual(context.exception.status, 413)

    def test_preserves_method_case_and_rejects_bad_percent_escape(self) -> None:
        parser = RequestParser()
        parser.feed(b"get /ok HTTP/1.1\r\nHost: test\r\n\r\n")
        request = parser.pop_request()
        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.method, "get")

        parser.feed(b"GET /bad%ZZ HTTP/1.1\r\nHost: test\r\n\r\n")
        with self.assertRaises(HTTPError) as context:
            parser.pop_request()
        self.assertEqual(context.exception.code, "invalid_percent_encoding")

    def test_request_json_reports_content_type_and_syntax(self) -> None:
        request = Request(
            method="POST",
            target="/",
            version="HTTP/1.1",
            headers=Headers(),
            body=b"{}",
            path="/",
            query={},
        )
        with self.assertRaises(HTTPError) as context:
            request.json()
        self.assertEqual(context.exception.status, 415)
        request.headers.set("Content-Type", "application/json")
        request.body = b"{"
        with self.assertRaises(HTTPError) as context:
            request.json()
        self.assertEqual(context.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
