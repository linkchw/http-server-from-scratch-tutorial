from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from task_api import build_app
from tinyhttp import Headers, Request


class TaskAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary.name) / "tasks.db"
        self.app = build_app(self.database)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def call(self, method: str, target: str, document=None):
        parsed = urlsplit(target)
        body = b""
        headers = Headers({"Host": "test"})
        if document is not None:
            body = json.dumps(document).encode("utf-8")
            headers.set("Content-Type", "application/json")
            headers.set("Content-Length", str(len(body)))
        request = Request(
            method=method,
            target=target,
            version="HTTP/1.1",
            headers=headers,
            body=body,
            path=parsed.path,
            query=parse_qs(parsed.query, keep_blank_values=True),
        )
        return self.app.handle(request)

    def test_full_crud_lifecycle(self) -> None:
        created = self.call(
            "POST",
            "/tasks",
            {
                "title": "Understand TCP streams",
                "description": "Practice fragmented reads",
                "priority": "high",
                "due_date": "2026-12-01",
            },
        )
        self.assertEqual(created.status, 201)
        self.assertEqual(created.headers.get("Location"), "/tasks/1")
        task = json.loads(created.body)
        self.assertEqual(task["status"], "todo")

        fetched = self.call("GET", "/tasks/1")
        self.assertEqual(fetched.status, 200)
        self.assertEqual(json.loads(fetched.body)["title"], "Understand TCP streams")

        patched = self.call("PATCH", "/tasks/1", {"status": "done"})
        self.assertEqual(json.loads(patched.body)["status"], "done")

        replaced = self.call(
            "PUT",
            "/tasks/1",
            {"title": "Review HTTP", "priority": "low"},
        )
        replaced_task = json.loads(replaced.body)
        self.assertEqual(replaced_task["description"], "")
        self.assertEqual(replaced_task["priority"], "low")

        deleted = self.call("DELETE", "/tasks/1")
        self.assertEqual(deleted.status, 204)
        self.assertEqual(self.call("GET", "/tasks/1").status, 404)

    def test_filter_pagination_and_search(self) -> None:
        self.call("POST", "/tasks", {"title": "Alpha HTTP", "status": "todo"})
        self.call("POST", "/tasks", {"title": "Beta SQL", "status": "done"})
        response = self.call("GET", "/tasks?status=todo&q=HTTP&limit=1&offset=0")
        document = json.loads(response.body)
        self.assertEqual(document["total"], 1)
        self.assertEqual(document["items"][0]["title"], "Alpha HTTP")

    def test_validation_problem_is_structured(self) -> None:
        response = self.call(
            "POST",
            "/tasks",
            {"title": "", "status": "almost", "unexpected": True},
        )
        self.assertEqual(response.status, 422)
        self.assertIn("application/problem+json", response.headers.get("Content-Type") or "")
        problem = json.loads(response.body)
        self.assertEqual(problem["type"], "urn:task-api:problem:validation-error")
        self.assertIn("title", problem["errors"])

    def test_query_validation_and_sql_shaped_search(self) -> None:
        invalid = self.call("GET", "/tasks?limit=1000&unknown=yes")
        self.assertEqual(invalid.status, 422)
        safe = self.call("GET", "/tasks?q=%25%27%20OR%201%3D1--")
        self.assertEqual(safe.status, 200)
        self.assertEqual(json.loads(safe.body)["total"], 0)

    def test_requires_content_length_on_body_endpoint(self) -> None:
        response = self.call("POST", "/tasks")
        self.assertEqual(response.status, 411)


if __name__ == "__main__":
    unittest.main()

