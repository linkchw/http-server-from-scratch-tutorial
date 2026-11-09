from __future__ import annotations

import json
import unittest

from tinyhttp import Application, Headers, Request, Response


def request(method: str, path: str) -> Request:
    return Request(
        method=method,
        target=path,
        version="HTTP/1.1",
        headers=Headers({"Host": "test"}),
        body=b"",
        path=path,
        query={},
    )


class ApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Application()

        @self.app.route("GET", "/users/me")
        def me(current: Request) -> Response:
            return Response.json({"kind": "static"})

        @self.app.route("GET", "/users/{user_id}")
        def user(current: Request) -> Response:
            return Response.json({"id": current.path_params["user_id"]})

    def test_static_route_precedes_parameter_route(self) -> None:
        response = self.app.handle(request("GET", "/users/me"))
        self.assertEqual(json.loads(response.body), {"kind": "static"})

    def test_parameter_is_exposed_on_request(self) -> None:
        response = self.app.handle(request("GET", "/users/42"))
        self.assertEqual(json.loads(response.body), {"id": "42"})

    def test_head_falls_back_to_get(self) -> None:
        response = self.app.handle(request("HEAD", "/users/me"))
        self.assertEqual(response.status, 200)

    def test_options_and_method_errors(self) -> None:
        options = self.app.handle(request("OPTIONS", "/users/me"))
        self.assertEqual(options.status, 204)
        self.assertIn("GET", options.headers.get("Allow") or "")
        not_allowed = self.app.handle(request("POST", "/users/me"))
        self.assertEqual(not_allowed.status, 405)
        self.assertIn("GET", not_allowed.headers.get("Allow") or "")
        missing = self.app.handle(request("GET", "/missing"))
        self.assertEqual(missing.status, 404)

    def test_middleware_wraps_handler_in_registration_order(self) -> None:
        events: list[str] = []

        def first(current: Request, next_handler):
            events.append("first-before")
            response = next_handler(current)
            events.append("first-after")
            return response

        def second(current: Request, next_handler):
            events.append("second-before")
            response = next_handler(current)
            events.append("second-after")
            return response

        self.app.add_middleware(first)
        self.app.add_middleware(second)
        self.app.handle(request("GET", "/users/me"))
        self.assertEqual(
            events,
            ["first-before", "second-before", "second-after", "first-after"],
        )


if __name__ == "__main__":
    unittest.main()
