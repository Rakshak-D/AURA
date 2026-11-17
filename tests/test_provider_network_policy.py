from __future__ import annotations

import asyncio
import math
import ssl
from collections.abc import Iterable

import httpcore
import pytest

from backend.app.providers.contracts import ProviderConnectionContext, ProviderId
from backend.app.providers.errors import ProviderError, ProviderErrorCode
from backend.app.providers.endpoint_policy import EndpointPolicy, LocalNetworkGrant
from backend.app.providers.transport import ProviderTransport, TransportLimits


class FakeResolver:
    def __init__(self, answers: Iterable[str] = ()) -> None:
        self.answers = tuple(answers)
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        self.calls.append((host, port))
        return self.answers


class FakeClock:
    def __init__(self) -> None:
        self.value = 10.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeNetworkStream(httpcore.AsyncNetworkStream):
    def __init__(
        self,
        response: bytes,
        *,
        chunk_size: int = 65_536,
        read_error: BaseException | None = None,
        write_error: BaseException | None = None,
        split_headers: bool = False,
    ) -> None:
        self.response = response
        self.chunk_size = chunk_size
        self.request_bytes = bytearray()
        self.closed = False
        self.tls_hostname: str | None = None
        self.ssl_context: ssl.SSLContext | None = None
        self.read_timeouts: list[float | None] = []
        self.write_timeouts: list[float | None] = []
        self.read_error = read_error
        self.write_error = write_error
        self.read_count = 0
        self.split_headers = split_headers or read_error is not None

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        self.read_count += 1
        if self.read_error is not None and self.read_count > 1:
            raise self.read_error
        self.read_timeouts.append(timeout)
        if self.split_headers and self.read_count == 1:
            head, separator, remaining = self.response.partition(b"\r\n\r\n")
            if separator:
                self.response = remaining
                return head + separator
        count = min(max_bytes, self.chunk_size, len(self.response))
        result, self.response = self.response[:count], self.response[count:]
        return result

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.write_timeouts.append(timeout)
        self.request_bytes.extend(buffer)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> FakeNetworkStream:
        self.ssl_context = ssl_context
        self.tls_hostname = server_hostname
        return self

    def get_extra_info(self, info: str) -> object | None:
        return None


class FakeNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(
        self,
        responses: Iterable[bytes] = (),
        *,
        read_error: BaseException | None = None,
        write_error: BaseException | None = None,
    ) -> None:
        self.responses = list(responses)
        self.connect_calls: list[tuple[str, int, float | None]] = []
        self.streams: list[FakeNetworkStream] = []
        self.sleep_calls: list[float] = []
        self.connect_error: BaseException | None = None
        self.read_error = read_error
        self.write_error = write_error

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> FakeNetworkStream:
        self.connect_calls.append((host, port, timeout))
        if self.connect_error is not None:
            raise self.connect_error
        response = (
            self.responses.pop(0)
            if self.responses
            else b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok"
        )
        stream = FakeNetworkStream(
            response,
            read_error=self.read_error,
            write_error=self.write_error,
            split_headers=self.read_error is not None,
        )
        self.streams.append(stream)
        return stream

    async def connect_unix_socket(self, *args, **kwargs):
        raise AssertionError(
            "provider transport must use the validated TCP destination"
        )

    async def sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)


def response_bytes(
    status: int = 200,
    body: bytes = b"ok",
    headers: bytes = b"Content-Type: application/json\r\n",
) -> bytes:
    return (
        f"HTTP/1.1 {status} Test\r\n".encode()
        + headers
        + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
        + body
    )


def context(
    base_url: str,
    *,
    provider: ProviderId = ProviderId.OPENAI_COMPATIBLE,
    local_only: bool = False,
    revision: int = 4,
) -> ProviderConnectionContext:
    return ProviderConnectionContext(
        user_id=19,
        connection_id="provider-connection-19",
        provider_id=provider,
        config_revision=revision,
        local_only=local_only,
        base_url=base_url,
    )


def policy(
    answers: Iterable[str] = (),
    *,
    grants: Iterable[LocalNetworkGrant] = (),
) -> tuple[EndpointPolicy, FakeResolver]:
    resolver = FakeResolver(answers)
    return EndpointPolicy(
        resolver=resolver, local_network_grants=tuple(grants)
    ), resolver


def transport(
    endpoint_policy: EndpointPolicy,
    backend: FakeNetworkBackend,
    *,
    limits: TransportLimits | None = None,
    clock=None,
) -> ProviderTransport:
    return ProviderTransport(
        endpoint_policy=endpoint_policy,
        network_backend_factory=lambda: backend,
        limits=limits,
        monotonic=clock,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "limit_override",
    [
        {"_response_limit": 1_000_000_000},
        {"_enforce_stream_duration": False},
    ],
)
def test_public_stream_api_cannot_override_hard_limits(
    limit_override: dict[str, object],
) -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    backend = FakeNetworkBackend((response_bytes(),))
    client = transport(endpoint_policy, backend)
    with pytest.raises(TypeError):
        client.stream(
            "GET",
            "https://api.example.com/events",
            context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
            **limit_override,
        )
    assert backend.connect_calls == []


@pytest.mark.unit
@pytest.mark.parametrize("local_only", [True, False])
@pytest.mark.parametrize(
    ("url", "expected_ip"),
    [
        ("http://127.0.0.1:11434", "127.0.0.1"),
        ("http://[::1]:11434", "::1"),
    ],
)
def test_explicit_loopback_is_allowed_independently_of_local_only(
    url: str,
    expected_ip: str,
    local_only: bool,
) -> None:
    endpoint_policy, resolver = policy()
    pinned = asyncio.run(
        endpoint_policy.resolve_and_pin(url, context(url, local_only=local_only))
    )
    assert str(pinned.numeric_ip) == expected_ip
    assert resolver.calls == []


@pytest.mark.unit
def test_local_only_defaults_to_enabled() -> None:
    assert (
        ProviderConnectionContext(
            user_id=1,
            connection_id="c1",
            provider_id=ProviderId.OLLAMA,
            config_revision=0,
            base_url="http://127.0.0.1:11434",
        ).local_only
        is True
    )


@pytest.mark.unit
def test_localhost_is_allowed_only_when_every_dns_answer_is_loopback() -> None:
    endpoint_policy, resolver = policy(("127.0.0.1", "::1"))
    pinned = asyncio.run(
        endpoint_policy.resolve_and_pin(
            "http://localhost:11434", context("http://localhost:11434", local_only=True)
        )
    )
    assert str(pinned.numeric_ip) == "127.0.0.1"
    assert resolver.calls == [("localhost", 11434)]


@pytest.mark.unit
@pytest.mark.parametrize(
    "answers", [("127.0.0.1", "192.168.1.8"), ("127.0.0.1", "8.8.8.8"), ("127.0.0.2",)]
)
def test_localhost_with_nonapproved_resolution_is_blocked(
    answers: tuple[str, ...],
) -> None:
    endpoint_policy, _ = policy(answers)
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            endpoint_policy.resolve_and_pin(
                "http://localhost:11434",
                context("http://localhost:11434", local_only=True),
            )
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED


@pytest.mark.unit
@pytest.mark.parametrize("url", ["http://192.168.1.20:11434", "http://nas.lan:11434"])
def test_lan_endpoint_fails_closed_without_trusted_connection_authorization(
    url: str,
) -> None:
    endpoint_policy, resolver = policy(("192.168.1.20",))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            endpoint_policy.resolve_and_pin(
                url, context(url, provider=ProviderId.OLLAMA, local_only=False)
            )
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == []


@pytest.mark.unit
def test_exact_connection_scoped_lan_grant_allows_one_validated_private_address() -> (
    None
):
    grant = LocalNetworkGrant(
        user_id=19,
        connection_id="provider-connection-19",
        config_revision=4,
        host="nas.lan",
        address="192.168.1.20",
        port=11434,
    )
    endpoint_policy, resolver = policy(("192.168.1.20",), grants=(grant,))
    local_context = context(
        "http://nas.lan:11434", provider=ProviderId.OPENAI_COMPATIBLE, local_only=True
    )
    pinned = asyncio.run(
        endpoint_policy.resolve_and_pin("http://nas.lan:11434/api/tags", local_context)
    )
    assert str(pinned.numeric_ip) == "192.168.1.20"
    assert resolver.calls == [("nas.lan", 11434)]


@pytest.mark.unit
def test_lan_grant_cannot_be_reused_by_a_different_user() -> None:
    grant = LocalNetworkGrant(
        user_id=19,
        connection_id="provider-connection-19",
        config_revision=4,
        host="192.168.1.20",
        address="192.168.1.20",
        port=11434,
    )
    endpoint_policy, resolver = policy(grants=(grant,))
    other_user = ProviderConnectionContext(
        user_id=20,
        connection_id="provider-connection-19",
        provider_id=ProviderId.OLLAMA,
        config_revision=4,
        local_only=False,
        base_url="http://192.168.1.20:11434",
    )
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            endpoint_policy.resolve_and_pin("http://192.168.1.20:11434", other_user)
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    ("answers", "revision"),
    [(("192.168.1.21",), 4), (("192.168.1.20", "8.8.8.8"), 4), (("192.168.1.20",), 5)],
)
def test_lan_grant_does_not_authorize_changed_or_mixed_destinations(
    answers: tuple[str, ...],
    revision: int,
) -> None:
    grant = LocalNetworkGrant(
        user_id=19,
        connection_id="provider-connection-19",
        config_revision=4,
        host="nas.lan",
        address="192.168.1.20",
        port=11434,
    )
    endpoint_policy, _ = policy(answers, grants=(grant,))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            endpoint_policy.resolve_and_pin(
                "http://nas.lan:11434/api/tags",
                context(
                    "http://nas.lan:11434",
                    provider=ProviderId.OLLAMA,
                    local_only=True,
                    revision=revision,
                ),
            )
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED


@pytest.mark.unit
def test_cloud_https_endpoint_accepts_only_a_public_resolution() -> None:
    endpoint_policy, resolver = policy(("93.184.216.34",))
    pinned = asyncio.run(
        endpoint_policy.resolve_and_pin(
            "https://api.example.com/v1",
            context("https://api.example.com/v1", provider=ProviderId.ANTHROPIC),
        )
    )
    assert str(pinned.numeric_ip) == "93.184.216.34"
    assert pinned.original_host == "api.example.com"
    assert resolver.calls == [("api.example.com", 443)]


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "http://api.example.com/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.8/v1",
        "https://169.254.169.254/latest/meta-data",
        "https://169.254.170.2/",
        "https://100.100.100.200/",
        "https://[fd00:ec2::254]/",
        "https://[fd20:ce::254]/",
        "https://[fc00::1]/",
        "https://[fe80::1]/",
        "https://[::ffff:127.0.0.1]/",
        "https://[::ffff:10.0.0.8]/",
        "https://[::ffff:169.254.169.254]/",
        "https://0.0.0.0/",
        "https://[::]/",
        "https://224.0.0.1/",
        "https://[ff02::1]/",
        "https://192.0.2.1/",
        "https://[2001:db8::1]/",
        "https://100.64.0.1/",
        "https://198.18.0.1/",
        "https://240.0.0.1/",
    ],
)
def test_cloud_endpoint_rejects_nonpublic_destinations(url: str) -> None:
    endpoint_policy, resolver = policy()
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            endpoint_policy.resolve_and_pin(
                url, context(url, provider=ProviderId.ANTHROPIC)
            )
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == []


@pytest.mark.unit
def test_cloud_hostname_with_mixed_public_and_private_answers_is_rejected() -> None:
    endpoint_policy, _ = policy(("93.184.216.34", "10.1.2.3"))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            endpoint_policy.resolve_and_pin(
                "https://api.example.com",
                context("https://api.example.com", provider=ProviderId.ANTHROPIC),
            )
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED


@pytest.mark.unit
def test_empty_or_malformed_dns_answers_fail_closed() -> None:
    for answers in ((), ("not-an-ip",)):
        endpoint_policy, _ = policy(answers)
        with pytest.raises(ProviderError) as caught:
            asyncio.run(
                endpoint_policy.resolve_and_pin(
                    "https://api.example.com",
                    context("https://api.example.com", provider=ProviderId.ANTHROPIC),
                )
            )
        assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED


@pytest.mark.unit
@pytest.mark.parametrize("timeout", [True, 0, -1, math.inf, math.nan])
def test_endpoint_policy_rejects_unbounded_or_invalid_resolution_timeout(
    timeout: float,
) -> None:
    with pytest.raises(ValueError, match="resolution_timeout"):
        EndpointPolicy(resolution_timeout=timeout)


@pytest.mark.unit
@pytest.mark.parametrize("timeout", [True, 0, -1, math.inf, math.nan])
def test_per_request_resolution_timeout_rejects_unbounded_or_invalid_values(
    timeout: float,
) -> None:
    endpoint_policy, resolver = policy(("93.184.216.34",))
    with pytest.raises(ValueError, match="resolution_timeout"):
        asyncio.run(
            endpoint_policy.resolve_and_pin(
                "https://api.example.com",
                context("https://api.example.com", provider=ProviderId.ANTHROPIC),
                resolution_timeout=timeout,
            )
        )
    assert resolver.calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@api.example.com/v1",
        "https://api.example.com:/v1",
        "https://api.example.com:99999/v1",
        "https://api.example.com/v1#fragment",
        "ftp://api.example.com/v1",
        "https://2130706433/v1",
        "https://127.1/v1",
        "http://api.example.com/v1\\@evil.example",
        "https://api.example.com/v1?api_key=secret",
        "https://api.example.com/v1?api-key=secret",
        "socks5://127.0.0.1:1080",
        "https://[invalid-ip]/v1",
        "https://api.example.com/v1\r\nX-Injected: yes",
    ],
)
def test_unsafe_or_ambiguous_urls_are_rejected(url: str) -> None:
    endpoint_policy, resolver = policy(("93.184.216.34",))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(
            endpoint_policy.resolve_and_pin(
                url, context(url, provider=ProviderId.ANTHROPIC)
            )
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("use_stream", [False, True])
@pytest.mark.asyncio
async def test_local_only_blocks_cloud_before_resolution_or_connection(
    use_stream: bool,
) -> None:
    endpoint_policy, resolver = policy(("93.184.216.34",))
    backend = FakeNetworkBackend((response_bytes(),))
    client = transport(endpoint_policy, backend)
    cloud_context = context(
        "https://api.example.com/v1", provider=ProviderId.ANTHROPIC, local_only=True
    )

    with pytest.raises(ProviderError) as caught:
        if use_stream:
            async with client.stream(
                "POST",
                "https://api.example.com/v1/chat",
                headers={"Authorization": "Bearer SENTINEL-SECRET"},
                body=b"SENTINEL-REQUEST",
                context=cloud_context,
            ):
                pass
        else:
            await client.request(
                "POST",
                "https://api.example.com/v1/chat",
                headers={"Authorization": "Bearer SENTINEL-SECRET"},
                body=b"SENTINEL-REQUEST",
                context=cloud_context,
            )

    assert caught.value.code is ProviderErrorCode.LOCAL_ONLY_BLOCKED
    assert resolver.calls == []
    assert backend.connect_calls == []
    assert backend.streams == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_url_and_headers_cannot_override_server_local_only_policy() -> (
    None
):
    endpoint_policy, resolver = policy()
    backend = FakeNetworkBackend()
    client = transport(endpoint_policy, backend)
    with pytest.raises(ProviderError) as caught:
        await client.request(
            "POST",
            "https://api.example.com/v1/chat?local_only=false",
            headers={"X-Local-Only": "false", "Authorization": "Bearer SENTINEL"},
            body=b"SENTINEL",
            context=context(
                "https://api.example.com/v1",
                provider=ProviderId.ANTHROPIC,
                local_only=True,
            ),
        )
    assert caught.value.code is ProviderErrorCode.LOCAL_ONLY_BLOCKED
    assert resolver.calls == []
    assert backend.connect_calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer SENTINEL\r\nX-Injected: yes"},
        {"Authorization": "Bearer SENTINEL\twith-tab"},
        {"Bad Header": "value"},
        {"Proxy-Authorization": "Basic SENTINEL"},
    ],
)
@pytest.mark.asyncio
async def test_malformed_or_proxy_headers_are_rejected_before_network(
    headers: dict[str, str],
) -> None:
    endpoint_policy, resolver = policy(("93.184.216.34",))
    backend = FakeNetworkBackend()
    with pytest.raises(ProviderError) as caught:
        await transport(endpoint_policy, backend).request(
            "POST",
            "https://api.example.com/v1/chat",
            headers=headers,
            body=b"payload",
            context=context(
                "https://api.example.com/v1", provider=ProviderId.ANTHROPIC
            ),
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == [("api.example.com", 443)]
    assert backend.connect_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_transport_pins_peer_and_preserves_tls_hostname_and_http_host() -> None:
    endpoint_policy, resolver = policy(("93.184.216.34",))
    backend = FakeNetworkBackend((response_bytes(),))
    client = transport(
        endpoint_policy,
        backend,
        limits=TransportLimits(
            connect_timeout=7, read_timeout=8, write_timeout=9, pool_timeout=2
        ),
    )
    result = await client.request(
        "POST",
        "https://api.example.com:8443/v1/chat?stream=0",
        headers={"Host": "attacker.invalid", "Authorization": "Bearer SENTINEL-SECRET"},
        body=b"payload",
        context=context(
            "https://api.example.com:8443/v1", provider=ProviderId.ANTHROPIC
        ),
    )
    stream = backend.streams[0]
    assert result.status_code == 200
    assert result.body == b"ok"
    assert resolver.calls == [("api.example.com", 8443)]
    assert backend.connect_calls == [("93.184.216.34", 8443, 7)]
    assert stream.tls_hostname == "api.example.com"
    assert stream.ssl_context is not None
    assert stream.ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert stream.ssl_context.check_hostname is True
    assert b"host: api.example.com:8443\r\n" in bytes(stream.request_bytes)
    assert b"attacker.invalid" not in bytes(stream.request_bytes)
    assert stream.write_timeouts and set(stream.write_timeouts) == {9}
    assert stream.read_timeouts and set(stream.read_timeouts) == {8}
    assert stream.closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_numeric_literal_is_pinned_without_resolver_call() -> None:
    endpoint_policy, resolver = policy()
    backend = FakeNetworkBackend((response_bytes(),))
    await transport(endpoint_policy, backend).request(
        "GET",
        "https://93.184.216.34/status",
        context=context("https://93.184.216.34", provider=ProviderId.OPENAI_COMPATIBLE),
    )
    assert resolver.calls == []
    assert backend.connect_calls[0][0] == "93.184.216.34"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_redirect_response_is_rejected_without_following_location() -> None:
    endpoint_policy, resolver = policy(("93.184.216.34",))
    backend = FakeNetworkBackend(
        (response_bytes(302, b"", b"Location: http://10.0.0.8/\r\n"),)
    )
    with pytest.raises(ProviderError) as caught:
        await transport(endpoint_policy, backend).request(
            "GET",
            "https://api.example.com/status",
            headers={"Authorization": "Bearer SENTINEL-SECRET"},
            context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == [("api.example.com", 443)]
    assert len(backend.connect_calls) == 1
    assert b"authorization: Bearer SENTINEL-SECRET" in bytes(
        backend.streams[0].request_bytes
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ambient_proxy_environment_does_not_change_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.setenv(name, "http://SENTINEL-PROXY.invalid:8000")
    monkeypatch.setenv("SSL_CERT_FILE", "Z:\\AURA-NONEXISTENT-CERT.pem")
    monkeypatch.setenv("SSL_CERT_DIR", "Z:\\AURA-NONEXISTENT-CERTS")
    endpoint_policy, _ = policy(("93.184.216.34",))
    backend = FakeNetworkBackend((response_bytes(),))
    await transport(endpoint_policy, backend).request(
        "GET",
        "https://api.example.com/",
        context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
    )
    assert backend.connect_calls[0][0] == "93.184.216.34"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dns_rebinding_is_revalidated_for_each_request() -> None:
    resolver = FakeResolver(("93.184.216.34",))

    async def rotate(host: str, port: int) -> tuple[str, ...]:
        resolver.calls.append((host, port))
        return ("93.184.216.34",) if len(resolver.calls) == 1 else ("169.254.169.254",)

    resolver.resolve = rotate
    endpoint_policy = EndpointPolicy(resolver=resolver)
    backend = FakeNetworkBackend((response_bytes(),))
    client = transport(endpoint_policy, backend)
    connection = context("https://api.example.com", provider=ProviderId.ANTHROPIC)
    await client.request("GET", "https://api.example.com/status", context=connection)
    with pytest.raises(ProviderError) as caught:
        await client.request(
            "GET", "https://api.example.com/status", context=connection
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == [("api.example.com", 443), ("api.example.com", 443)]
    assert backend.connect_calls == [("93.184.216.34", 443, 5.0)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_each_configuration_revision_resolves_and_opens_a_fresh_connection() -> (
    None
):
    endpoint_policy, resolver = policy(("93.184.216.34",))
    backend = FakeNetworkBackend((response_bytes(), response_bytes()))
    client = transport(endpoint_policy, backend)
    await client.request(
        "GET",
        "https://api.example.com/status",
        context=context(
            "https://api.example.com", provider=ProviderId.ANTHROPIC, revision=4
        ),
    )
    await client.request(
        "GET",
        "https://api.example.com/status",
        context=context(
            "https://api.example.com", provider=ProviderId.ANTHROPIC, revision=5
        ),
    )
    assert resolver.calls == [("api.example.com", 443), ("api.example.com", 443)]
    assert backend.connect_calls == [
        ("93.184.216.34", 443, 5.0),
        ("93.184.216.34", 443, 5.0),
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_streaming_enforces_cumulative_byte_limit_and_closes_resources() -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    backend = FakeNetworkBackend((response_bytes(body=b"123456"),))
    limits = TransportLimits(max_streamed_response_bytes=5)
    stream_response = transport(endpoint_policy, backend, limits=limits).stream(
        "GET",
        "https://api.example.com/events",
        context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
    )
    with pytest.raises(ProviderError) as caught:
        async with stream_response as response:
            async for _chunk in response:
                pass
    assert caught.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert backend.streams[0].closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_streaming_rejects_compressed_body_without_decompressing() -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    backend = FakeNetworkBackend(
        (response_bytes(headers=b"Content-Encoding: gzip\r\n"),)
    )
    with pytest.raises(ProviderError) as caught:
        async with transport(endpoint_policy, backend).stream(
            "GET",
            "https://api.example.com/events",
            context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
        ):
            pass
    assert caught.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert backend.streams[0].closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_request_response_limit_is_incremental_and_closes_resources() -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    backend = FakeNetworkBackend((response_bytes(body=b"123456"),))
    with pytest.raises(ProviderError) as caught:
        await transport(
            endpoint_policy, backend, limits=TransportLimits(max_response_bytes=5)
        ).request(
            "GET",
            "https://api.example.com/data",
            context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert backend.streams[0].closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_oversized_response_headers_are_rejected_and_closed() -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    oversized_headers = b"X-Pad: 12345678901234567890\r\n"
    backend = FakeNetworkBackend((response_bytes(headers=oversized_headers),))
    with pytest.raises(ProviderError) as caught:
        await transport(
            endpoint_policy,
            backend,
            limits=TransportLimits(max_response_header_bytes=10),
        ).request(
            "GET",
            "https://api.example.com/data",
            context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
        )
    assert caught.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert backend.streams[0].closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_duration_uses_monotonic_deadline_without_sleeping() -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    chunked_response = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        b"5\r\nfirst\r\n6\r\nsecond\r\n0\r\n\r\n"
    )
    backend = FakeNetworkBackend((chunked_response,))
    clock = FakeClock()
    stream_response = transport(
        endpoint_policy,
        backend,
        limits=TransportLimits(max_stream_duration=1.0),
        clock=clock,
    ).stream(
        "GET",
        "https://api.example.com/events",
        context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
    )
    with pytest.raises(ProviderError) as caught:
        async with stream_response as response:
            assert await response.__anext__() == b"first"
            clock.advance(2.0)
            await response.__anext__()
    assert caught.value.code is ProviderErrorCode.TIMEOUT
    assert backend.streams[0].closed is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancelled_request_releases_network_resources() -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    backend = FakeNetworkBackend()
    backend.connect_error = asyncio.CancelledError()
    with pytest.raises(ProviderError) as caught:
        await transport(endpoint_policy, backend).request(
            "GET",
            "https://api.example.com/",
            context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
        )
    assert caught.value.code is ProviderErrorCode.CANCELLED
    assert backend.connect_calls == [("93.184.216.34", 443, 5.0)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_cancellation_closes_the_response_and_connection() -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    header_only = b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\nConnection: close\r\n\r\n"
    backend = FakeNetworkBackend((header_only,), read_error=asyncio.CancelledError())
    stream_response = transport(endpoint_policy, backend).stream(
        "GET",
        "https://api.example.com/events",
        context=context("https://api.example.com", provider=ProviderId.ANTHROPIC),
    )
    with pytest.raises(ProviderError) as caught:
        async with stream_response as response:
            await response.__anext__()
    assert caught.value.code is ProviderErrorCode.CANCELLED
    assert backend.streams[0].closed is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("failure_point", "error_type"),
    [
        ("connect", httpcore.ConnectTimeout),
        ("write", httpcore.WriteTimeout),
        ("read", httpcore.ReadTimeout),
    ],
)
@pytest.mark.asyncio
async def test_connect_read_and_write_timeouts_are_normalized(
    failure_point: str,
    error_type: type[BaseException],
) -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    sentinel_error = error_type("SENTINEL-TIMEOUT-DETAIL")
    backend = FakeNetworkBackend(
        (response_bytes(),),
        read_error=sentinel_error if failure_point == "read" else None,
        write_error=sentinel_error if failure_point == "write" else None,
    )
    if failure_point == "connect":
        backend.connect_error = sentinel_error
    with pytest.raises(ProviderError) as caught:
        await transport(endpoint_policy, backend).request(
            "POST" if failure_point == "write" else "GET",
            "https://api.example.com/v1/chat",
            body=b"request" if failure_point == "write" else None,
            context=context(
                "https://api.example.com/v1", provider=ProviderId.ANTHROPIC
            ),
        )
    assert caught.value.code is ProviderErrorCode.TIMEOUT
    assert "SENTINEL-TIMEOUT-DETAIL" not in str(caught.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_failure_is_sanitized_and_not_retried(
    caplog: pytest.LogCaptureFixture,
) -> None:
    endpoint_policy, _ = policy(("93.184.216.34",))
    backend = FakeNetworkBackend()
    backend.connect_error = httpcore.ConnectError(
        "SENTINEL-SECRET at https://SENTINEL-SECRET.invalid"
    )
    with pytest.raises(ProviderError) as caught:
        await transport(endpoint_policy, backend).request(
            "POST",
            "https://api.example.com/v1/chat",
            headers={"Authorization": "Bearer SENTINEL-SECRET"},
            body=b"SENTINEL-PROMPT",
            context=context(
                "https://api.example.com/v1", provider=ProviderId.ANTHROPIC
            ),
        )
    assert caught.value.code is ProviderErrorCode.UNAVAILABLE
    assert "SENTINEL" not in str(caught.value)
    assert "SENTINEL" not in caplog.text
    assert backend.connect_calls and len(backend.connect_calls) == 1
    assert backend.sleep_calls == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_connection_pool_acquisition_has_a_bounded_wait() -> None:
    endpoint_policy, _ = policy(("127.0.0.1",))
    backend = FakeNetworkBackend((response_bytes(),))
    client = transport(
        endpoint_policy,
        backend,
        limits=TransportLimits(max_concurrent_requests=1, pool_timeout=0),
    )
    open_stream = client.stream(
        "GET",
        "http://127.0.0.1:11434/events",
        context=context(
            "http://127.0.0.1:11434", provider=ProviderId.OLLAMA, local_only=True
        ),
    )
    async with open_stream:
        with pytest.raises(ProviderError) as caught:
            await client.request(
                "GET",
                "http://127.0.0.1:11434/status",
                context=context(
                    "http://127.0.0.1:11434",
                    provider=ProviderId.OLLAMA,
                    local_only=True,
                ),
            )
    assert caught.value.code is ProviderErrorCode.TIMEOUT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_url_cannot_cross_the_stored_connection_origin() -> None:
    endpoint_policy, resolver = policy(("93.184.216.34",))
    backend = FakeNetworkBackend()
    with pytest.raises(ProviderError) as caught:
        await transport(endpoint_policy, backend).request(
            "POST",
            "https://attacker.example/v1/chat",
            headers={"Authorization": "Bearer SENTINEL"},
            body=b"SENTINEL",
            context=context(
                "https://api.example.com/v1", provider=ProviderId.ANTHROPIC
            ),
        )
    assert caught.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == []
    assert backend.connect_calls == []


@pytest.mark.unit
def test_policy_has_no_import_time_dns_or_socket_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError(
            "network lookup must not occur during ordinary construction"
        )

    monkeypatch.setattr("socket.getaddrinfo", fail)
    endpoint_policy = EndpointPolicy()
    client = ProviderTransport(endpoint_policy=endpoint_policy)
    assert client is not None
