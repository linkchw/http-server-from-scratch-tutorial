"""Incremental, strict parsing for the supported HTTP/1.1 request subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

from .models import Headers, HTTPError, Request


TOKEN = re.compile(rb"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
INVALID_VALUE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ParserLimits:
    request_line: int = 8 * 1024
    header_bytes: int = 32 * 1024
    header_count: int = 100
    body_bytes: int = 1024 * 1024


class RequestParser:
    """Accept bytes over time and return complete requests one at a time."""

    def __init__(self, limits: ParserLimits | None = None) -> None:
        self.limits = limits or ParserLimits()
        self._buffer = bytearray()

    @property
    def has_buffered_data(self) -> bool:
        return bool(self._buffer)

    def feed(self, data: bytes) -> None:
        self._buffer.extend(data)
        if b"\r\n" not in self._buffer and len(self._buffer) > self.limits.request_line:
            raise HTTPError(414, "The request target is too long.", code="uri_too_long")
        if b"\r\n\r\n" not in self._buffer and len(self._buffer) > self.limits.header_bytes:
            raise HTTPError(
                431,
                "The request header section is too large.",
                code="headers_too_large",
            )

    def pop_request(
        self,
        client: tuple[str, int] | None = None,
    ) -> Request | None:
        marker = self._buffer.find(b"\r\n\r\n")
        if marker < 0:
            return None
        head_end = marker + 4
        if head_end > self.limits.header_bytes:
            raise HTTPError(
                431,
                "The request header section is too large.",
                code="headers_too_large",
            )
        head = bytes(self._buffer[:marker])
        if self._contains_bare_line_break(head):
            raise HTTPError(400, "HTTP lines must end with CRLF.", code="invalid_line_end")
        lines = head.split(b"\r\n")
        if not lines or len(lines[0]) > self.limits.request_line:
            raise HTTPError(414, "The request line is too long.", code="uri_too_long")
        method, target, version = self._parse_request_line(lines[0])
        headers = self._parse_headers(lines[1:])
        content_length = self._content_length(headers)
        total = head_end + content_length
        if len(self._buffer) < total:
            return None
        body = bytes(self._buffer[head_end:total])
        del self._buffer[:total]
        path, query = self._parse_target(target)
        return Request(
            method=method,
            target=target,
            version=version,
            headers=headers,
            body=body,
            path=path,
            query=query,
            client=client,
        )

    @staticmethod
    def _contains_bare_line_break(value: bytes) -> bool:
        return re.search(rb"(?<!\r)\n|\r(?!\n)", value) is not None

    @staticmethod
    def _parse_request_line(line: bytes) -> tuple[str, str, str]:
        parts = line.split(b" ")
        if len(parts) != 3 or not all(parts):
            raise HTTPError(400, "Malformed request line.", code="invalid_request_line")
        method_raw, target_raw, version_raw = parts
        if not TOKEN.fullmatch(method_raw):
            raise HTTPError(400, "Invalid request method.", code="invalid_method")
        try:
            method = method_raw.decode("ascii")
            target = target_raw.decode("ascii")
            version = version_raw.decode("ascii")
        except UnicodeDecodeError as error:
            raise HTTPError(
                400,
                "The request line must contain ASCII bytes.",
                code="invalid_request_line",
            ) from error
        if version != "HTTP/1.1":
            raise HTTPError(
                505,
                "This educational server supports HTTP/1.1 only.",
                code="http_version_not_supported",
            )
        return method, target, version

    def _parse_headers(self, lines: list[bytes]) -> Headers:
        if len(lines) > self.limits.header_count:
            raise HTTPError(431, "Too many header fields.", code="too_many_headers")
        headers = Headers()
        for line in lines:
            if line.startswith((b" ", b"\t")):
                raise HTTPError(
                    400,
                    "Obsolete folded header lines are not accepted.",
                    code="folded_header",
                )
            name_raw, separator, value_raw = line.partition(b":")
            if not separator or not TOKEN.fullmatch(name_raw):
                raise HTTPError(400, "Malformed header field.", code="invalid_header")
            name = name_raw.decode("ascii")
            value = value_raw.decode("iso-8859-1").strip(" \t")
            if INVALID_VALUE.search(value):
                raise HTTPError(
                    400,
                    "A header contains a forbidden control character.",
                    code="invalid_header_value",
                )
            headers.add(name, value)
        hosts = headers.get_all("Host")
        if len(hosts) != 1 or not hosts[0]:
            raise HTTPError(
                400,
                "HTTP/1.1 requires exactly one non-empty Host header.",
                code="invalid_host",
            )
        return headers

    def _content_length(self, headers: Headers) -> int:
        transfer_encodings = headers.get_all("Transfer-Encoding")
        lengths = headers.get_all("Content-Length")
        if transfer_encodings and lengths:
            raise HTTPError(
                400,
                "Transfer-Encoding and Content-Length cannot be combined.",
                code="ambiguous_framing",
            )
        if transfer_encodings:
            raise HTTPError(
                501,
                "Transfer-Encoding is explained in the book but not implemented.",
                code="transfer_encoding_not_implemented",
            )
        if len(lengths) > 1:
            raise HTTPError(
                400,
                "Duplicate Content-Length fields are rejected.",
                code="ambiguous_content_length",
            )
        if not lengths:
            return 0
        try:
            length = int(lengths[0], 10)
        except ValueError as error:
            raise HTTPError(
                400,
                "Content-Length must be a non-negative decimal integer.",
                code="invalid_content_length",
            ) from error
        if length < 0:
            raise HTTPError(
                400,
                "Content-Length cannot be negative.",
                code="invalid_content_length",
            )
        if length > self.limits.body_bytes:
            raise HTTPError(
                413,
                "The request body exceeds the configured limit.",
                code="body_too_large",
            )
        return length

    @staticmethod
    def _parse_target(target: str) -> tuple[str, dict[str, list[str]]]:
        if target == "*":
            return "*", {}
        if not target.startswith("/"):
            raise HTTPError(
                400,
                "Only origin-form request targets are supported.",
                code="unsupported_request_target",
            )
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            raise HTTPError(400, "Invalid origin-form target.", code="invalid_target")
        if re.search(r"%(?![0-9A-Fa-f]{2})", target):
            raise HTTPError(
                400,
                "The request target contains an invalid percent escape.",
                code="invalid_percent_encoding",
            )
        try:
            segments = [unquote(segment, errors="strict") for segment in parsed.path.split("/")]
        except UnicodeDecodeError as error:
            raise HTTPError(
                400,
                "The request path contains invalid UTF-8 percent encoding.",
                code="invalid_path_encoding",
            ) from error
        path = "/".join(segments) or "/"
        try:
            query = parse_qs(
                parsed.query,
                keep_blank_values=True,
                strict_parsing=False,
                encoding="utf-8",
                errors="strict",
            )
        except UnicodeDecodeError as error:
            raise HTTPError(
                400,
                "The query string contains invalid UTF-8 percent encoding.",
                code="invalid_query_encoding",
            ) from error
        return path, query
