"""Static provider catalogue; adapter construction is deferred to later A1 work."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from .contracts import ProviderId


@dataclass(frozen=True, slots=True)
class ProviderDefinition:
    provider_id: ProviderId
    display_name: str
    embedding_only: bool = False


DEFAULT_PROVIDER_DEFINITIONS = (
    ProviderDefinition(ProviderId.OLLAMA, "Ollama"),
    ProviderDefinition(ProviderId.OPENAI_COMPATIBLE, "OpenAI-compatible"),
    ProviderDefinition(ProviderId.LEGACY_GGUF, "Legacy GGUF"),
    ProviderDefinition(ProviderId.ANTHROPIC, "Anthropic"),
    ProviderDefinition(ProviderId.GEMINI, "Gemini"),
    ProviderDefinition(
        ProviderId.SENTENCE_TRANSFORMERS,
        "Sentence Transformers (local embeddings)",
        embedding_only=True,
    ),
)


class ProviderRegistry:
    """Lookup for approved provider definitions without importing adapters."""

    def __init__(
        self,
        definitions: Sequence[ProviderDefinition] = DEFAULT_PROVIDER_DEFINITIONS,
    ) -> None:
        entries = tuple(definitions)
        indexed: dict[ProviderId, ProviderDefinition] = {}
        for definition in entries:
            if definition.provider_id in indexed:
                raise ValueError(f"duplicate provider definition: {definition.provider_id}")
            indexed[definition.provider_id] = definition
        self._definitions = entries
        self._by_id: Mapping[ProviderId, ProviderDefinition] = MappingProxyType(indexed)

    @property
    def definitions(self) -> tuple[ProviderDefinition, ...]:
        return self._definitions

    def get(self, provider_id: ProviderId | str) -> ProviderDefinition:
        try:
            normalized = ProviderId(provider_id)
        except (TypeError, ValueError):
            raise KeyError("provider definition not found") from None
        try:
            return self._by_id[normalized]
        except KeyError:
            raise KeyError("provider definition not found") from None


DEFAULT_PROVIDER_REGISTRY = ProviderRegistry()
