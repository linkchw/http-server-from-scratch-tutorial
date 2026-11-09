"""Public request, response, header, and error types."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Iterable, Iterator, Mapping


HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class Headers:
    """An ordered, case-insensitive, multi-value HTTP header collection."""

    def __init__(
        self,
        values: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
    ) -> None:
        self._items: list[tuple[str, str]] = []
        if values is None:
            return
        source = values.items() if isinstance(values, Mapping) else values
        for name, value in source:
            self.add(name, value)

    def add(self, name: str, value: str) -> None:
        normalized_name = str(name)
        normalized_value = str(value)
        if not HEADER_NAME.fullmatch(normalized_name):
            raise ValueError(f"Invalid HTTP header name: {normalized_name!r}")
        if any(
            ord(character) < 32 and character != "\t" or ord(character) == 127
            for character in normalized_value
        ):
            raise ValueError("HTTP header values cannot contain control characters")
        self._items.append((normalized_name, normalized_value))

    def set(self, name: str, value: str) -> None:
        lowered = name.casefold()
        self._items = [
            (old_name, old_value)
            for old_name, old_value in self._items
            if old_name.casefold() != lowered
        ]
        self.add(name, value)

    def remove(self, name: str) -> None:
        lowered = name.casefold()
        self._items = [
            (old_name, value)
            for old_name, value in self._items
            if old_name.casefold() != lowered
        ]

    def get(self, name: str, default: str | None = None) -> str | None:
        lowered = name.casefold()
        for old_name, value in reversed(self._items):
            if old_name.casefold() == lowered:
                return value
        return default

    def get_all(self, name: str) -> list[str]:
        lowered = name.casefold()
        return [
            value for old_name, value in self._items if old_name.casefold() == lowered
        ]

    def copy(self) -> "Headers":
        return Headers(self._items)

    def items(self) -> list[tuple[str, str]]:
        return list(self._items)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.get(name) is not None

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"Headers({self._items!r})"


class HTTPError(Exception):
    """An expected error that can safely become an HTTP problem response."""

    def __init__(
        self,
        status: int,
        detail: str,
        *,
        code: str | None = None,
        title: str | None = None,
        errors: Mapping[str, str] | None = None,
        type_uri: str | None = None,
    ) -> None:
        self.status = status
        self.detail = detail
        self.code = code or HTTPStatus(status).phrase.lower().replace(" ", "_")
        self.title = title or HTTPStatus(status).phrase
        self.errors = dict(errors or {})
        self.type_uri = type_uri or f"urn:tinyhttp:problem:{self.code}"
        super().__init__(detail)


@dataclass(slots=True)
class Request:
    method: str
    target: str
    version: str
    headers: Headers
    body: bytes
    path: str
    query: dict[str, list[str]]
    client: tuple[str, int] | None = None
    path_params: dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        media_type = (self.headers.get("Content-Type") or "").split(";", 1)[0]
        if media_type.strip().casefold() != "application/json":
            raise HTTPError(
                415,
                "This endpoint requires Content-Type: application/json.",
                code="unsupported_media_type",
            )
        try:
            text = self.body.decode("utf-8")
        except UnicodeDecodeError as error:
            raise HTTPError(
                400,
                "The JSON body must be valid UTF-8.",
                code="invalid_utf8",
            ) from error
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise HTTPError(
                400,
                f"Malformed JSON at line {error.lineno}, column {error.colno}.",
                code="invalid_json",
            ) from error


@dataclass(slots=True)
class Response:
    status: int = 200
    body: bytes = b""
    headers: Headers = field(default_factory=Headers)

    def __post_init__(self) -> None:
        if not isinstance(self.body, bytes):
            raise TypeError("Response body must be bytes")
        if not isinstance(self.headers, Headers):
            self.headers = Headers(self.headers)

    @classmethod
    def json(
        cls,
        value: Any,
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> "Response":
        body = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        result_headers = Headers(headers)
        result_headers.set("Content-Type", "application/json; charset=utf-8")
        return cls(status=status, body=body, headers=result_headers)

    @classmethod
    def problem(
        cls,
        status: int,
        detail: str,
        *,
        instance: str | None = None,
        code: str | None = None,
        title: str | None = None,
        errors: Mapping[str, str] | None = None,
        type_uri: str | None = None,
    ) -> "Response":
        resolved_code = code or HTTPStatus(status).phrase.lower().replace(" ", "_")
        document: dict[str, Any] = {
            "type": type_uri or f"urn:tinyhttp:problem:{resolved_code}",
            "title": title or HTTPStatus(status).phrase,
            "status": status,
            "detail": detail,
        }
        if instance is not None:
            document["instance"] = instance
        if errors:
            document["errors"] = dict(errors)
        response = cls.json(document, status=status)
        response.headers.set(
            "Content-Type", "application/problem+json; charset=utf-8"
        )
        return response
