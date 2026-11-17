"""Policy-enforcing async HTTP transport for future provider adapters."""

from __future__ import annotations

import asyncio
import math
import re
import ssl
import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Callable

import httpcore
import httpx

from .contracts import ProviderConnectionContext
from .endpoint_policy import EndpointPolicy, PinnedDestination
from .errors import ProviderError, ProviderErrorCode, normalize_provider_error

_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass(frozen=True, slots=True)
class TransportLimits:
    """Conservative bounded defaults for one shared provider transport."""

    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    write_timeout: float = 10.0
    pool_timeout: float = 5.0
    max_response_bytes: int = 1_048_576
    max_streamed_response_bytes: int = 4_194_304
    max_stream_duration: float = 120.0
    max_concurrent_requests: int = 10
    max_response_header_bytes: int = 65_536

    def __post_init__(self) -> None:
        for name in (
            "connect_timeout",
            "read_timeout",
            "write_timeout",
            "max_stream_duration",
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} must be a finite positive number")
        if (
            isinstance(self.pool_timeout, bool)
            or not isinstance(self.pool_timeout, (int, float))
            or not math.isfinite(self.pool_timeout)
            or self.pool_timeout < 0
        ):
            raise ValueError("pool_timeout must be a finite non-negative number")
        for name in (
            "max_response_bytes",
            "max_streamed_response_bytes",
            "max_concurrent_requests",
            "max_response_header_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    status_code: int
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    body: bytes = field(repr=False)


def _safe_transport_error(error: BaseException) -> ProviderError:
    if isinstance(error, ProviderError):
        return error
    if isinstance(error, asyncio.CancelledError):
        return ProviderError(ProviderErrorCode.CANCELLED)
    if isinstance(
        error, (TimeoutError, asyncio.TimeoutError, httpcore.TimeoutException)
    ):
        return ProviderError(ProviderErrorCode.TIMEOUT, retryable=True)
    if isinstance(error, httpcore.NetworkError):
        return ProviderError(ProviderErrorCode.UNAVAILABLE, retryable=True)
    if isinstance(error, httpcore.ProtocolError):
        return ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return normalize_provider_error(error)


def _verified_ssl_context() -> ssl.SSLContext:
    context = httpx.create_ssl_context(trust_env=False)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return context


def _header_value(value: str) -> bytes:
    if not isinstance(value, str) or any(
        ord(char) < 32 or ord(char) > 126 for char in value
    ):
        raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)
    try:
        return value.encode("ascii")
    except UnicodeEncodeError:
        raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED) from None


class ProviderTransport:
    """Async provider HTTP boundary with per-operation validation and pinning.

    A fresh HTTPCore pool is created for every request and closed afterward.
    Keep-alive and HTTP/2 are disabled so connections cannot cross users,
    endpoint revisions, or policy contexts.
    """

    def __init__(
        self,
        *,
        endpoint_policy: EndpointPolicy | None = None,
        network_backend_factory: Callable[[], httpcore.AsyncNetworkBackend | None]
        | None = None,
        limits: TransportLimits | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self.endpoint_policy = endpoint_policy or EndpointPolicy()
        self._network_backend_factory = network_backend_factory or (lambda: None)
        self.limits = limits or TransportLimits()
        self._monotonic = monotonic or time.monotonic
        self._pool_semaphore = asyncio.Semaphore(self.limits.max_concurrent_requests)

    async def request(
        self,
        method: str,
        url: str,
        *,
        context: ProviderConnectionContext,
        headers: Mapping[str, str] | None = None,
        body: bytes | str | None = None,
    ) -> ProviderResponse:
        """Send one bounded request and return an in-memory bounded response."""

        response_headers: tuple[tuple[str, str], ...]
        status_code: int
        body_bytes = bytearray()
        async with self._create_stream(
            method,
            url,
            context=context,
            headers=headers,
            body=body,
            response_limit=self.limits.max_response_bytes,
            duration_limit=None,
        ) as response:
            status_code = response.status_code
            response_headers = response.headers
            async for chunk in response:
                body_bytes.extend(chunk)
        return ProviderResponse(status_code, response_headers, bytes(body_bytes))

    def stream(
        self,
        method: str,
        url: str,
        *,
        context: ProviderConnectionContext,
        headers: Mapping[str, str] | None = None,
        body: bytes | str | None = None,
    ) -> ProviderStreamResponse:
        """Create an async context-managed response stream.

        The response body is available only while used as ``async with``; this
        guarantees explicit cleanup when iteration ends or is cancelled.
        """

        return self._create_stream(
            method,
            url,
            context=context,
            headers=headers,
            body=body,
            response_limit=self.limits.max_streamed_response_bytes,
            duration_limit=self.limits.max_stream_duration,
        )

    def _create_stream(
        self,
        method: str,
        url: str,
        *,
        context: ProviderConnectionContext,
        headers: Mapping[str, str] | None,
        body: bytes | str | None,
        response_limit: int,
        duration_limit: float | None,
    ) -> ProviderStreamResponse:
        """Construct a stream with limits selected by this transport only."""

        return ProviderStreamResponse(
            transport=self,
            method=method,
            url=url,
            context=context,
            headers=headers or {},
            body=body,
            response_limit=response_limit,
            duration_limit=duration_limit,
        )

    async def _acquire_pool_slot(self) -> None:
        if not self._pool_semaphore.locked():
            await self._pool_semaphore.acquire()
            return
        if self.limits.pool_timeout == 0:
            raise ProviderError(ProviderErrorCode.TIMEOUT, retryable=True)
        try:
            await asyncio.wait_for(
                self._pool_semaphore.acquire(), timeout=self.limits.pool_timeout
            )
        except (asyncio.TimeoutError, TimeoutError):
            raise ProviderError(ProviderErrorCode.TIMEOUT, retryable=True) from None
        except asyncio.CancelledError:
            raise ProviderError(ProviderErrorCode.CANCELLED) from None

    def _create_pool(self) -> httpcore.AsyncConnectionPool:
        try:
            return httpcore.AsyncConnectionPool(
                ssl_context=_verified_ssl_context(),
                proxy=None,
                max_connections=1,
                max_keepalive_connections=0,
                keepalive_expiry=0.0,
                http1=True,
                http2=False,
                retries=0,
                network_backend=self._network_backend_factory(),
            )
        except ProviderError:
            raise
        except Exception as error:
            raise _safe_transport_error(error) from None

    def _build_request(
        self,
        method: str,
        destination: PinnedDestination,
        headers: Mapping[str, str],
        body: bytes | str | None,
    ) -> httpcore.Request:
        if not isinstance(method, str) or method.upper() not in {"GET", "POST"}:
            raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)
        if body is None:
            request_body = b""
        elif isinstance(body, str):
            request_body = body.encode("utf-8")
        elif isinstance(body, bytes):
            request_body = body
        else:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)

        raw_headers: list[tuple[bytes, bytes]] = [
            (b"host", destination.host_header.encode("ascii")),
            (b"accept-encoding", b"identity"),
            (b"user-agent", b"AURA provider transport"),
        ]
        if request_body:
            raw_headers.append(
                (b"content-length", str(len(request_body)).encode("ascii"))
            )
        try:
            seen_headers: set[str] = set()
            for name, value in headers.items():
                if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
                    raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)
                normalized_name = name.lower()
                if normalized_name in seen_headers:
                    raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)
                seen_headers.add(normalized_name)
                if normalized_name in _HOP_BY_HOP_HEADERS:
                    raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)
                if normalized_name in {"host", "accept-encoding", "content-length"}:
                    continue
                raw_headers.append(
                    (normalized_name.encode("ascii"), _header_value(value))
                )
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED) from None

        peer_host = str(destination.numeric_ip).encode("ascii")
        request_url = httpcore.URL(
            scheme=destination.scheme.encode("ascii"),
            host=peer_host,
            port=destination.port,
            target=destination.request_target,
        )
        return httpcore.Request(
            method=method.upper().encode("ascii"),
            url=request_url,
            headers=raw_headers,
            content=request_body,
            extensions={
                "sni_hostname": destination.tls_server_name,
                "timeout": {
                    "connect": self.limits.connect_timeout,
                    "read": self.limits.read_timeout,
                    "write": self.limits.write_timeout,
                    "pool": self.limits.pool_timeout,
                },
            },
        )


class ProviderStreamResponse:
    """Single-use async response stream with byte/time bounds and cleanup."""

    def __init__(
        self,
        *,
        transport: ProviderTransport,
        method: str,
        url: str,
        context: ProviderConnectionContext,
        headers: Mapping[str, str],
        body: bytes | str | None,
        response_limit: int,
        duration_limit: float | None,
    ) -> None:
        self._transport = transport
        self._method = method
        self._url = url
        self._context = context
        self._headers = headers
        self._body = body
        self._response_limit = response_limit
        self._duration_limit = duration_limit
        self._pool: httpcore.AsyncConnectionPool | None = None
        self._response: httpcore.Response | None = None
        self._iterator: AsyncIterator[bytes] | None = None
        self._entered = False
        self._closed = False
        self._lease_acquired = False
        self._bytes_read = 0
        self._started_at = 0.0
        self.status_code = 0
        self.headers: tuple[tuple[str, str], ...] = ()

    async def __aenter__(self) -> ProviderStreamResponse:
        if self._entered or self._closed:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        self._entered = True
        self._started_at = self._transport._monotonic()
        try:
            self._transport.endpoint_policy.preflight_local_only(self._context)
            await self._transport._acquire_pool_slot()
            self._lease_acquired = True

            async def open_response() -> httpcore.Response:
                destination = await self._transport.endpoint_policy.resolve_and_pin(
                    self._url,
                    self._context,
                    resolution_timeout=self._transport.limits.connect_timeout,
                )
                self._pool = self._transport._create_pool()
                request = self._transport._build_request(
                    self._method, destination, self._headers, self._body
                )
                return await self._pool.handle_async_request(request)

            if self._duration_limit is None:
                self._response = await open_response()
            else:
                remaining = self._remaining_duration()
                if remaining <= 0:
                    raise ProviderError(ProviderErrorCode.TIMEOUT, retryable=True)
                self._response = await asyncio.wait_for(
                    open_response(), timeout=remaining
                )
            self.status_code = self._response.status
            self.headers = self._safe_headers(self._response.headers)
            if 300 <= self.status_code < 400:
                raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)
            if (
                len(self.headers)
                and sum(len(name) + len(value) for name, value in self.headers)
                > self._transport.limits.max_response_header_bytes
            ):
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            encodings = [
                value.strip().casefold()
                for name, value in self.headers
                if name == "content-encoding"
            ]
            if any(encoding not in {"", "identity"} for encoding in encodings):
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            self._iterator = self._response.stream.__aiter__()
            return self
        except asyncio.CancelledError:
            await self.aclose()
            raise ProviderError(ProviderErrorCode.CANCELLED) from None
        except ProviderError:
            await self.aclose()
            raise
        except Exception as error:
            await self.aclose()
            raise _safe_transport_error(error) from None

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.aclose()

    def __aiter__(self) -> ProviderStreamResponse:
        return self

    async def __anext__(self) -> bytes:
        if self._closed or self._iterator is None:
            raise StopAsyncIteration
        remaining = self._remaining_duration()
        if self._duration_limit is not None and remaining <= 0:
            await self.aclose()
            raise ProviderError(ProviderErrorCode.TIMEOUT, retryable=True)
        try:
            if self._duration_limit is None:
                chunk = await self._iterator.__anext__()
            else:
                chunk = await asyncio.wait_for(
                    self._iterator.__anext__(), timeout=remaining
                )
        except StopAsyncIteration:
            await self.aclose()
            raise
        except asyncio.CancelledError:
            await self.aclose()
            raise ProviderError(ProviderErrorCode.CANCELLED) from None
        except (asyncio.TimeoutError, TimeoutError):
            await self.aclose()
            raise ProviderError(ProviderErrorCode.TIMEOUT, retryable=True) from None
        except Exception as error:
            await self.aclose()
            raise _safe_transport_error(error) from None

        if self._duration_limit is not None and self._remaining_duration() <= 0:
            await self.aclose()
            raise ProviderError(ProviderErrorCode.TIMEOUT, retryable=True)
        self._bytes_read += len(chunk)
        if self._bytes_read > self._response_limit:
            await self.aclose()
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        return chunk

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        cleanup = asyncio.create_task(self._close_resources())
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(cleanup)
            except BaseException:
                pass
            raise

    async def _close_resources(self) -> None:
        try:
            if self._response is not None:
                await self._response.aclose()
        except BaseException:
            pass
        try:
            if self._pool is not None:
                await self._pool.aclose()
        except BaseException:
            pass
        finally:
            if self._lease_acquired:
                self._lease_acquired = False
                self._transport._pool_semaphore.release()

    def _remaining_duration(self) -> float:
        if self._duration_limit is None:
            return math.inf
        return self._duration_limit - (self._transport._monotonic() - self._started_at)

    @staticmethod
    def _safe_headers(
        headers: tuple[tuple[bytes, bytes], ...],
    ) -> tuple[tuple[str, str], ...]:
        try:
            return tuple(
                (name.decode("ascii").lower(), value.decode("latin-1"))
                for name, value in headers
            )
        except (UnicodeDecodeError, AttributeError, TypeError):
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
