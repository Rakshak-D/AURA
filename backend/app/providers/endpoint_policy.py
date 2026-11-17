"""Strict endpoint parsing, destination policy, and numeric-IP pinning."""

from __future__ import annotations

import asyncio
import ipaddress
import math
import re
import socket
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import parse_qsl, quote, urlsplit

from .contracts import ProviderConnectionContext, ProviderId
from .errors import ProviderError, ProviderErrorCode

_MAX_URL_LENGTH = 2_048
_MAX_HOST_LENGTH = 253
_ALLOWED_METHOD_SCHEMES = {"http", "https"}
_AMBIGUOUS_NUMERIC_HOST = re.compile(
    r"(?i)^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+))*$"
)
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_HEADER_QUERY_SECRETS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_key",
    "client_secret",
    "key",
    "password",
    "secret",
    "secret_key",
    "subscription_key",
    "token",
    "x_api_key",
    "x_goog_api_key",
}
_METADATA_HOSTNAMES = {
    "instance-data",
    "instance-data.ec2.internal",
    "metadata",
    "metadata.google.com",
    "metadata.google.internal",
}
_METADATA_ADDRESSES = tuple(
    ipaddress.ip_network(value)
    for value in (
        "169.254.169.254/32",
        "169.254.170.2/32",
        "100.100.100.200/32",
        "fd00:ec2::254/128",
        "fd20:ce::254/128",
    )
)
_PRIVATE_LAN_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)
_LOCAL_PROVIDER_IDS = {
    ProviderId.OLLAMA,
    ProviderId.LEGACY_GGUF,
    ProviderId.SENTENCE_TRANSFORMERS,
}
_CLOUD_PROVIDER_IDS = {ProviderId.ANTHROPIC, ProviderId.GEMINI}


class Resolver(Protocol):
    """The only DNS interface used by endpoint policy."""

    async def resolve(self, host: str, port: int) -> Sequence[str]: ...


class SystemResolver:
    """Resolve a hostname at request time without opening a connection."""

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        loop = asyncio.get_running_loop()
        results = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        addresses: list[str] = []
        for family, _socktype, _protocol, _canonical_name, sockaddr in results:
            if family not in (socket.AF_INET, socket.AF_INET6):
                raise ValueError("unsupported address family")
            addresses.append(sockaddr[0])
        return tuple(addresses)


@dataclass(frozen=True, slots=True)
class PinnedDestination:
    """Validated single-peer request destination; request path is hidden."""

    original_host: str
    numeric_ip: ipaddress.IPv4Address | ipaddress.IPv6Address
    port: int
    scheme: str
    request_target: bytes = field(repr=False)
    host_header: str
    tls_server_name: str


@dataclass(frozen=True, slots=True)
class LocalNetworkGrant:
    """Trusted server-owned, exact host/address/port permission for one connection."""

    user_id: int
    connection_id: str
    config_revision: int
    host: str
    address: ipaddress.IPv4Address | ipaddress.IPv6Address | str
    port: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.user_id, int)
            or isinstance(self.user_id, bool)
            or self.user_id <= 0
            or not isinstance(self.connection_id, str)
            or not self.connection_id.strip()
            or not isinstance(self.config_revision, int)
            or isinstance(self.config_revision, bool)
            or self.config_revision < 0
        ):
            raise ValueError("LAN authorization identity is invalid")
        if (
            isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65_535
        ):
            raise ValueError("LAN authorization port is invalid")
        normalized_host, _host_ip = _parse_host(self.host)
        try:
            normalized_address = _normalize_ip(ipaddress.ip_address(self.address))
        except (TypeError, ValueError):
            raise ValueError("LAN authorization address is invalid") from None
        if not _is_private_lan_unicast(normalized_address):
            raise ValueError("LAN authorization must name a private unicast address")
        object.__setattr__(self, "host", normalized_host)
        object.__setattr__(self, "address", normalized_address)

    def matches_connection(
        self, context: ProviderConnectionContext, host: str, port: int
    ) -> bool:
        return (
            self.user_id == context.user_id
            and self.connection_id == context.connection_id
            and self.config_revision == context.config_revision
            and self.host == host
            and self.port == port
        )


@dataclass(frozen=True, slots=True)
class _ParsedEndpoint:
    scheme: str
    host: str
    numeric_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None
    port: int
    host_header: str
    request_target: bytes = field(repr=False)


def _endpoint_blocked() -> ProviderError:
    return ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)


def _validated_resolution_timeout(value: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError("resolution_timeout must be a finite positive number")
    return float(value)


def _normalize_ip(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped
    return address


def _parse_host(
    host: str,
) -> tuple[str, ipaddress.IPv4Address | ipaddress.IPv6Address | None]:
    if (
        not isinstance(host, str)
        or not host
        or "%" in host
        or len(host) > _MAX_HOST_LENGTH
        or not host.isascii()
    ):
        raise _endpoint_blocked()

    normalized = host.lower()
    try:
        address = _normalize_ip(ipaddress.ip_address(normalized))
        return str(address), address
    except ValueError:
        if _AMBIGUOUS_NUMERIC_HOST.fullmatch(normalized):
            raise _endpoint_blocked() from None

    if normalized.endswith(".") or len(normalized) > _MAX_HOST_LENGTH:
        raise _endpoint_blocked()
    labels = normalized.split(".")
    if any(not _DNS_LABEL.fullmatch(label) for label in labels):
        raise _endpoint_blocked()
    return normalized, None


def _parse_endpoint(url: str, *, allow_query: bool = True) -> _ParsedEndpoint:
    if (
        not isinstance(url, str)
        or not url
        or len(url) > _MAX_URL_LENGTH
        or "#" in url
        or "\\" in url
        or any(ord(character) < 32 or ord(character) == 127 for character in url)
    ):
        raise _endpoint_blocked()

    try:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if (
            scheme not in _ALLOWED_METHOD_SCHEMES
            or not parts.netloc
            or parts.username is not None
            or parts.password is not None
        ):
            raise _endpoint_blocked()
        if "@" in parts.netloc or parts.netloc.endswith(":"):
            raise _endpoint_blocked()
        if not parts.netloc.startswith("[") and parts.netloc.count(":") > 1:
            raise _endpoint_blocked()
        if parts.netloc.startswith("[") and "]" not in parts.netloc:
            raise _endpoint_blocked()
        host, address = _parse_host(parts.hostname or "")
        explicit_port = parts.port
        port = (
            explicit_port
            if explicit_port is not None
            else (443 if scheme == "https" else 80)
        )
        if not 1 <= port <= 65_535:
            raise _endpoint_blocked()
        if not allow_query and parts.query:
            raise _endpoint_blocked()
        if parts.query:
            for key, _value in parse_qsl(
                parts.query.replace(";", "&"),
                keep_blank_values=True,
                strict_parsing=False,
            ):
                normalized_key = key.casefold().replace("-", "_")
                if normalized_key in _HEADER_QUERY_SECRETS or any(
                    marker in normalized_key
                    for marker in (
                        "api_key",
                        "apikey",
                        "authorization",
                        "auth_token",
                        "access_token",
                        "password",
                        "secret",
                        "token",
                    )
                ):
                    raise _endpoint_blocked()
        if re.search(r"%(?![0-9a-fA-F]{2})", parts.path + parts.query):
            raise _endpoint_blocked()

        request_target = quote(
            parts.path or "/",
            safe="/%:@!$&'()*+,;=-._~",
        )
        if parts.query:
            request_target += "?" + quote(
                parts.query,
                safe="%!?&=+$,;:@'()*-._~/",
            )
        target_bytes = request_target.encode("ascii")
    except ProviderError:
        raise
    except (UnicodeEncodeError, ValueError, TypeError):
        raise _endpoint_blocked() from None

    authority_host = f"[{host}]" if isinstance(address, ipaddress.IPv6Address) else host
    default_port = 443 if scheme == "https" else 80
    host_header = authority_host if port == default_port else f"{authority_host}:{port}"
    return _ParsedEndpoint(scheme, host, address, port, host_header, target_bytes)


def _explicit_loopback(endpoint: _ParsedEndpoint) -> bool:
    if endpoint.host == "localhost":
        return True
    address = endpoint.numeric_ip
    return address in (ipaddress.IPv4Address("127.0.0.1"), ipaddress.IPv6Address("::1"))


def _is_public_unicast(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    normalized = _normalize_ip(address)
    return (
        normalized.is_global
        and not normalized.is_private
        and not normalized.is_loopback
        and not normalized.is_link_local
        and not normalized.is_multicast
        and not normalized.is_unspecified
        and not normalized.is_reserved
    )


def _is_private_lan_unicast(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    normalized = _normalize_ip(address)
    return (
        any(
            normalized.version == network.version and normalized in network
            for network in _PRIVATE_LAN_NETWORKS
        )
        and not any(
            normalized.version == network.version and normalized in network
            for network in _METADATA_ADDRESSES
        )
        and not normalized.is_loopback
        and not normalized.is_link_local
        and not normalized.is_multicast
        and not normalized.is_unspecified
        and not normalized.is_reserved
    )


def _destination_is_local(
    context: ProviderConnectionContext,
    configured_endpoint: _ParsedEndpoint,
    lan_grants: Sequence[LocalNetworkGrant],
) -> bool:
    try:
        provider_id = ProviderId(context.provider_id)
    except (TypeError, ValueError):
        raise _endpoint_blocked() from None
    if provider_id in _LOCAL_PROVIDER_IDS:
        return True
    if provider_id in _CLOUD_PROVIDER_IDS:
        return False
    if provider_id is ProviderId.OPENAI_COMPATIBLE:
        return _explicit_loopback(configured_endpoint) or any(
            grant.matches_connection(
                context, configured_endpoint.host, configured_endpoint.port
            )
            for grant in lan_grants
        )
    raise _endpoint_blocked()


class EndpointPolicy:
    """Resolve and validate stored provider endpoints before network access.

    LocalNetworkGrant is the internal contract for a trusted connection-scoped
    authorization source. A1-D does not connect this contract to persistence or
    Settings, so the default grant set is empty and LAN access fails closed.
    """

    def __init__(
        self,
        resolver: Resolver | None = None,
        *,
        local_network_grants: Sequence[LocalNetworkGrant] = (),
        resolution_timeout: float = 5.0,
    ) -> None:
        self._resolver = SystemResolver() if resolver is None else resolver
        self._lan_grants = tuple(local_network_grants)
        self._resolution_timeout = _validated_resolution_timeout(resolution_timeout)

    async def resolve_and_pin(
        self,
        url: str,
        context: ProviderConnectionContext,
        *,
        resolution_timeout: float | None = None,
    ) -> PinnedDestination:
        if resolution_timeout is not None:
            resolution_timeout = _validated_resolution_timeout(resolution_timeout)
        if type(context.local_only) is not bool:
            raise _endpoint_blocked()
        provider_id = ProviderId(context.provider_id)
        if context.local_only and provider_id in _CLOUD_PROVIDER_IDS:
            raise ProviderError(ProviderErrorCode.LOCAL_ONLY_BLOCKED)

        configured_endpoint = _parse_endpoint(context.base_url or "", allow_query=False)
        is_local = _destination_is_local(context, configured_endpoint, self._lan_grants)
        if context.local_only and not is_local:
            raise ProviderError(ProviderErrorCode.LOCAL_ONLY_BLOCKED)

        requested_endpoint = _parse_endpoint(url)
        if (
            requested_endpoint.scheme != configured_endpoint.scheme
            or requested_endpoint.host != configured_endpoint.host
            or requested_endpoint.port != configured_endpoint.port
        ):
            raise _endpoint_blocked()

        if requested_endpoint.host in _METADATA_HOSTNAMES:
            raise _endpoint_blocked()

        if is_local:
            if requested_endpoint.scheme not in ("http", "https"):
                raise _endpoint_blocked()
            if requested_endpoint.numeric_ip is not None:
                if _explicit_loopback(requested_endpoint):
                    addresses = (requested_endpoint.numeric_ip,)
                elif self._has_lan_host_grant(
                    context, requested_endpoint.host, requested_endpoint.port
                ):
                    addresses = (requested_endpoint.numeric_ip,)
                    if not self._all_lan_answers_authorized(
                        context, requested_endpoint, addresses
                    ):
                        raise _endpoint_blocked()
                else:
                    raise _endpoint_blocked()
            elif requested_endpoint.host == "localhost":
                addresses = await self._resolve_all(
                    requested_endpoint, resolution_timeout
                )
                if any(
                    address
                    not in (
                        ipaddress.IPv4Address("127.0.0.1"),
                        ipaddress.IPv6Address("::1"),
                    )
                    for address in addresses
                ):
                    raise _endpoint_blocked()
            elif self._has_lan_host_grant(
                context, requested_endpoint.host, requested_endpoint.port
            ):
                addresses = await self._resolve_all(
                    requested_endpoint, resolution_timeout
                )
                if not self._all_lan_answers_authorized(
                    context, requested_endpoint, addresses
                ):
                    raise _endpoint_blocked()
            else:
                # A private address alone is not a LAN authorization.
                raise _endpoint_blocked()
        else:
            if requested_endpoint.scheme != "https":
                raise _endpoint_blocked()
            if requested_endpoint.numeric_ip is not None:
                addresses = (requested_endpoint.numeric_ip,)
            else:
                addresses = await self._resolve_all(requested_endpoint)
            if not addresses or any(
                not _is_public_unicast(address) for address in addresses
            ):
                raise _endpoint_blocked()

        if not addresses:
            raise _endpoint_blocked()
        selected = sorted(set(addresses), key=lambda item: (item.version, int(item)))[0]
        return PinnedDestination(
            original_host=requested_endpoint.host,
            numeric_ip=selected,
            port=requested_endpoint.port,
            scheme=requested_endpoint.scheme,
            request_target=requested_endpoint.request_target,
            host_header=requested_endpoint.host_header,
            tls_server_name=requested_endpoint.host,
        )

    async def _resolve_all(
        self,
        endpoint: _ParsedEndpoint,
        timeout: float | None = None,
    ) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
        try:
            answers = await asyncio.wait_for(
                self._resolver.resolve(endpoint.host, endpoint.port),
                timeout=self._resolution_timeout if timeout is None else timeout,
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            raise ProviderError(ProviderErrorCode.TIMEOUT, retryable=True) from None
        except Exception:
            raise _endpoint_blocked() from None

        if not answers:
            raise _endpoint_blocked()
        parsed: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        try:
            for answer in answers:
                parsed.append(_normalize_ip(ipaddress.ip_address(answer)))
        except (TypeError, ValueError):
            raise _endpoint_blocked() from None
        return tuple(parsed)

    def _has_lan_host_grant(
        self, context: ProviderConnectionContext, host: str, port: int
    ) -> bool:
        return any(
            grant.matches_connection(context, host, port) for grant in self._lan_grants
        )

    def _all_lan_answers_authorized(
        self,
        context: ProviderConnectionContext,
        endpoint: _ParsedEndpoint,
        addresses: Sequence[ipaddress.IPv4Address | ipaddress.IPv6Address],
    ) -> bool:
        if not addresses:
            return False
        matching_grants = {
            grant.address
            for grant in self._lan_grants
            if grant.matches_connection(context, endpoint.host, endpoint.port)
        }
        return all(
            _is_private_lan_unicast(address) and address in matching_grants
            for address in addresses
        )
