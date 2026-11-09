"""Create and list tasks with the standard-library HTTP client."""

from __future__ import annotations

import http.client
import json


connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=5)
payload = json.dumps(
    {
        "title": "Read the HTTP message chapter",
        "priority": "high",
        "status": "in_progress",
    }
)
connection.request(
    "POST",
    "/tasks",
    body=payload.encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
created = connection.getresponse()
print(created.status, created.read().decode("utf-8"))

connection.request("GET", "/tasks?status=in_progress")
listed = connection.getresponse()
print(listed.status, listed.read().decode("utf-8"))
connection.close()

