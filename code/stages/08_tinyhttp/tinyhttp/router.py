"""A small segment router with static-route precedence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import Request, Response


Handler = Callable[[Request], Response]


@dataclass(slots=True)
class Route:
    method: str
    pattern: str
    segments: tuple[str, ...]
    handler: Handler
    parameter_count: int
    order: int

    def match(self, path: str) -> dict[str, str] | None:
        path_segments = tuple(segment for segment in path.split("/") if segment)
        if len(path_segments) != len(self.segments):
            return None
        parameters: dict[str, str] = {}
        for expected, actual in zip(self.segments, path_segments, strict=True):
            if expected.startswith("{") and expected.endswith("}"):
                parameters[expected[1:-1]] = actual
            elif expected != actual:
                return None
        return parameters


class Router:
    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, pattern: str, handler: Handler) -> None:
        if not pattern.startswith("/"):
            raise ValueError("Route patterns must start with /")
        segments = tuple(segment for segment in pattern.split("/") if segment)
        names = [
            segment[1:-1]
            for segment in segments
            if segment.startswith("{") and segment.endswith("}")
        ]
        if any(not name.isidentifier() for name in names) or len(names) != len(set(names)):
            raise ValueError(f"Invalid route parameter in {pattern!r}")
        normalized = method.upper()
        if any(route.method == normalized and route.pattern == pattern for route in self._routes):
            raise ValueError(f"Duplicate route: {normalized} {pattern}")
        self._routes.append(
            Route(
                method=normalized,
                pattern=pattern,
                segments=segments,
                handler=handler,
                parameter_count=len(names),
                order=len(self._routes),
            )
        )
        self._routes.sort(key=lambda route: (route.parameter_count, route.order))

    def resolve(
        self,
        method: str,
        path: str,
    ) -> tuple[Handler | None, dict[str, str], set[str]]:
        allowed: set[str] = set()
        candidate: tuple[Handler, dict[str, str]] | None = None
        for route in self._routes:
            parameters = route.match(path)
            if parameters is None:
                continue
            allowed.add(route.method)
            if route.method == method and candidate is None:
                candidate = (route.handler, parameters)
        if "GET" in allowed:
            allowed.add("HEAD")
        if allowed:
            allowed.add("OPTIONS")
        if candidate is None and method == "HEAD":
            return self.resolve("GET", path)
        if candidate is None:
            return None, {}, allowed
        return candidate[0], candidate[1], allowed

