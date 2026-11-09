"""HTTP resource handlers and validation for the Task API."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from tinyhttp import Application, HTTPError, Request, Response

from .database import Database, TaskRepository


STATUSES = {"todo", "in_progress", "done"}
PRIORITIES = {"low", "medium", "high"}
WRITABLE_FIELDS = {"title", "description", "status", "priority", "due_date"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_app(database_path: str | Path) -> Application:
    database = Database(database_path)
    database.initialize()
    repository = TaskRepository(database)
    app = Application()

    @app.route("GET", "/health")
    def health(request: Request) -> Response:
        return Response.json({"status": "ok"})

    @app.route("POST", "/tasks")
    def create_task(request: Request) -> Response:
        require_body(request)
        values = validate_task_document(request.json(), partial=False)
        now = utc_now()
        values.update(created_at=now, updated_at=now)
        task = repository.create(values)
        response = Response.json(task, status=201)
        response.headers.set("Location", f"/tasks/{task['id']}")
        return response

    @app.route("GET", "/tasks")
    def list_tasks(request: Request) -> Response:
        options = validate_list_query(request.query)
        items, total = repository.list(**options)
        return Response.json(
            {
                "items": items,
                "total": total,
                "limit": options["limit"],
                "offset": options["offset"],
            }
        )

    @app.route("GET", "/tasks/{task_id}")
    def get_task(request: Request) -> Response:
        task_id = path_id(request)
        task = repository.get(task_id)
        if task is None:
            raise not_found(task_id)
        return Response.json(task)

    @app.route("PUT", "/tasks/{task_id}")
    def replace_task(request: Request) -> Response:
        task_id = path_id(request)
        require_body(request)
        values = validate_task_document(request.json(), partial=False)
        values["updated_at"] = utc_now()
        task = repository.replace(task_id, values)
        if task is None:
            raise not_found(task_id)
        return Response.json(task)

    @app.route("PATCH", "/tasks/{task_id}")
    def update_task(request: Request) -> Response:
        task_id = path_id(request)
        require_body(request)
        values = validate_task_document(request.json(), partial=True)
        values["updated_at"] = utc_now()
        task = repository.update(task_id, values)
        if task is None:
            raise not_found(task_id)
        return Response.json(task)

    @app.route("DELETE", "/tasks/{task_id}")
    def delete_task(request: Request) -> Response:
        task_id = path_id(request)
        if not repository.delete(task_id):
            raise not_found(task_id)
        return Response(status=204)

    return app


def require_body(request: Request) -> None:
    if request.headers.get("Content-Length") is None:
        raise HTTPError(
            411,
            "This endpoint requires a Content-Length header.",
            code="length_required",
        )
    if not request.body:
        raise HTTPError(400, "The request body cannot be empty.", code="empty_body")


def path_id(request: Request) -> int:
    raw = request.path_params["task_id"]
    try:
        task_id = int(raw, 10)
    except ValueError as error:
        raise HTTPError(
            404,
            "Task identifiers are positive integers.",
            code="task_not_found",
        ) from error
    if task_id < 1:
        raise HTTPError(404, "Task not found.", code="task_not_found")
    return task_id


def not_found(task_id: int) -> HTTPError:
    return HTTPError(
        404,
        f"Task {task_id} does not exist.",
        code="task_not_found",
        type_uri="urn:task-api:problem:task-not-found",
    )


def validate_task_document(value: Any, *, partial: bool) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise validation_error({"body": "Expected a JSON object."})
    unknown = set(value) - WRITABLE_FIELDS
    errors: dict[str, str] = {}
    if unknown:
        errors["body"] = "Unknown fields: " + ", ".join(sorted(unknown))
    if partial and not value:
        errors["body"] = "PATCH requires at least one writable field."
    if not partial and "title" not in value:
        errors["title"] = "This field is required."

    result: dict[str, Any] = {}
    if "title" in value:
        title = value["title"]
        if not isinstance(title, str) or not title.strip():
            errors["title"] = "Must be a non-empty string."
        elif len(title.strip()) > 200:
            errors["title"] = "Must contain at most 200 characters."
        else:
            result["title"] = title.strip()
    elif not partial:
        result["title"] = ""

    if "description" in value:
        description = value["description"]
        if not isinstance(description, str):
            errors["description"] = "Must be a string."
        elif len(description) > 2000:
            errors["description"] = "Must contain at most 2000 characters."
        else:
            result["description"] = description
    elif not partial:
        result["description"] = ""

    validate_choice(value, result, errors, "status", STATUSES, "todo", partial)
    validate_choice(value, result, errors, "priority", PRIORITIES, "medium", partial)

    if "due_date" in value:
        due_date = value["due_date"]
        if due_date is not None:
            if not isinstance(due_date, str):
                errors["due_date"] = "Must be an ISO date or null."
            else:
                try:
                    parsed_date = date.fromisoformat(due_date)
                except ValueError:
                    errors["due_date"] = "Use the YYYY-MM-DD format."
                else:
                    if parsed_date.isoformat() != due_date:
                        errors["due_date"] = "Use the YYYY-MM-DD format."
                    else:
                        result["due_date"] = due_date
        else:
            result["due_date"] = None
    elif not partial:
        result["due_date"] = None

    if errors:
        raise validation_error(errors)
    return result


def validate_choice(
    source: Mapping[str, Any],
    target: dict[str, Any],
    errors: dict[str, str],
    name: str,
    choices: set[str],
    default: str,
    partial: bool,
) -> None:
    if name in source:
        value = source[name]
        if not isinstance(value, str) or value not in choices:
            errors[name] = "Must be one of: " + ", ".join(sorted(choices))
        else:
            target[name] = value
    elif not partial:
        target[name] = default


def validate_list_query(query: dict[str, list[str]]) -> dict[str, Any]:
    supported = {"status", "priority", "due_before", "q", "limit", "offset"}
    unknown = set(query) - supported
    errors: dict[str, str] = {}
    if unknown:
        errors["query"] = "Unknown parameters: " + ", ".join(sorted(unknown))
    values: dict[str, str | None] = {}
    for name in supported:
        candidates = query.get(name, [])
        if len(candidates) > 1:
            errors[name] = "May be provided only once."
        values[name] = candidates[0] if candidates else None
    if values["status"] and values["status"] not in STATUSES:
        errors["status"] = "Must be one of: " + ", ".join(sorted(STATUSES))
    if values["priority"] and values["priority"] not in PRIORITIES:
        errors["priority"] = "Must be one of: " + ", ".join(sorted(PRIORITIES))
    if values["due_before"]:
        try:
            parsed_due_before = date.fromisoformat(str(values["due_before"]))
        except ValueError:
            errors["due_before"] = "Use the YYYY-MM-DD format."
        else:
            if parsed_due_before.isoformat() != values["due_before"]:
                errors["due_before"] = "Use the YYYY-MM-DD format."
    limit = parse_query_integer(values["limit"], "limit", 20, minimum=1, maximum=100, errors=errors)
    offset = parse_query_integer(values["offset"], "offset", 0, minimum=0, maximum=1_000_000, errors=errors)
    search = values["q"]
    if search is not None and len(search) > 200:
        errors["q"] = "Must contain at most 200 characters."
    if errors:
        raise validation_error(errors)
    return {
        "status": values["status"],
        "priority": values["priority"],
        "due_before": values["due_before"],
        "search": search,
        "limit": limit,
        "offset": offset,
    }


def parse_query_integer(
    value: str | None,
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
    errors: dict[str, str],
) -> int:
    if value is None:
        return default
    try:
        result = int(value, 10)
    except ValueError:
        errors[name] = "Must be an integer."
        return default
    if not minimum <= result <= maximum:
        errors[name] = f"Must be between {minimum} and {maximum}."
    return result


def validation_error(errors: Mapping[str, str]) -> HTTPError:
    return HTTPError(
        422,
        "One or more values failed validation.",
        code="validation_error",
        title="Validation failed",
        errors=errors,
        type_uri="urn:task-api:problem:validation-error",
    )
