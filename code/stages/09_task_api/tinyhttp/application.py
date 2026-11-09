"""Routing, middleware composition, and safe application error handling."""

from __future__ import annotations

import logging
from collections.abc import Callable

from .models import HTTPError, Request, Response
from .router import Handler, Router


Middleware = Callable[[Request, Handler], Response]
SUPPORTED_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


class Application:
    def __init__(self) -> None:
        self.router = Router()
        self._middleware: list[Middleware] = []
        self.logger = logging.getLogger("tinyhttp.application")

    def route(self, method: str, pattern: str) -> Callable[[Handler], Handler]:
        def register(handler: Handler) -> Handler:
            self.router.add(method, pattern, handler)
            return handler

        return register

    def add_middleware(self, middleware: Middleware) -> None:
        self._middleware.append(middleware)

    def handle(self, request: Request) -> Response:
        try:
            if request.method not in SUPPORTED_METHODS:
                raise HTTPError(
                    501,
                    f"Method {request.method} is not implemented.",
                    code="method_not_implemented",
                )
            handler = self._dispatch
            for middleware in reversed(self._middleware):
                next_handler = handler

                def wrapped(
                    current: Request,
                    middleware: Middleware = middleware,
                    next_handler: Handler = next_handler,
                ) -> Response:
                    return middleware(current, next_handler)

                handler = wrapped
            response = handler(request)
            if not isinstance(response, Response):
                raise TypeError("Handlers must return a Response")
            return response
        except HTTPError as error:
            response = Response.problem(
                error.status,
                error.detail,
                instance=request.path,
                code=error.code,
                title=error.title,
                errors=error.errors,
                type_uri=error.type_uri,
            )
            if error.status == 405:
                _, _, allowed = self.router.resolve(request.method, request.path)
                response.headers.set("Allow", ", ".join(sorted(allowed)))
            return response
        except Exception:
            self.logger.exception("Unhandled application exception")
            return Response.problem(
                500,
                "The server encountered an unexpected error.",
                instance=request.path,
                code="internal_server_error",
            )

    def _dispatch(self, request: Request) -> Response:
        if request.path == "*" and request.method == "OPTIONS":
            response = Response(status=204)
            response.headers.set("Allow", ", ".join(sorted(SUPPORTED_METHODS)))
            return response
        handler, parameters, allowed = self.router.resolve(request.method, request.path)
        if request.method == "OPTIONS" and allowed:
            response = Response(status=204)
            response.headers.set("Allow", ", ".join(sorted(allowed)))
            return response
        if handler is None and allowed:
            raise HTTPError(
                405,
                f"Method {request.method} is not allowed for this resource.",
                code="method_not_allowed",
            )
        if handler is None:
            raise HTTPError(404, "No route matches this path.", code="not_found")
        request.path_params = parameters
        response = handler(request)
        if allowed and response.status == 405:
            response.headers.set("Allow", ", ".join(sorted(allowed)))
        return response


__all__ = ["Application", "Handler", "Middleware"]
