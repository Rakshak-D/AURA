from __future__ import annotations

import subprocess
import sys

import pytest

from backend.app.config import PROJECT_DIR


def _contracts():
    try:
        from backend.app.providers import contracts
    except ImportError as exc:
        pytest.fail(f"provider-independent contracts are not available: {exc}")
    return contracts


def _errors():
    try:
        from backend.app.providers import errors
    except ImportError as exc:
        pytest.fail(f"normalized provider errors are not available: {exc}")
    return errors


def _registry():
    try:
        from backend.app.providers import registry
    except ImportError as exc:
        pytest.fail(f"provider registry definitions are not available: {exc}")
    return registry


def test_provider_messages_accept_only_structured_roles():
    contracts = _contracts()

    message = contracts.ProviderMessage(role=contracts.MessageRole.USER, content="hello")

    assert message.role is contracts.MessageRole.USER
    assert message.content == "hello"
    with pytest.raises(ValueError):
        contracts.ProviderMessage(role="developer", content="hello")


def test_tool_messages_require_a_call_identity():
    contracts = _contracts()

    with pytest.raises(ValueError):
        contracts.ProviderMessage(role=contracts.MessageRole.TOOL, content="result")

    tool_message = contracts.ProviderMessage(
        role=contracts.MessageRole.TOOL,
        content="result",
        tool_call_id="call-123",
    )

    assert tool_message.tool_call_id == "call-123"


def test_chat_contract_represents_tool_declarations_calls_and_correlated_results():
    contracts = _contracts()
    definition = contracts.ToolDefinition(
        name="lookup_weather",
        input_schema={
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    )
    request = contracts.ChatRequest(
        model_id="model-a",
        messages=(contracts.ProviderMessage(contracts.MessageRole.USER, "Weather in Paris?"),),
        tools=(definition,),
    )
    proposed = contracts.ToolCall(
        call_id="provider-call-1",
        name="lookup_weather",
        arguments_json='{"city":"Paris"}',
    )
    assistant_message = contracts.ProviderMessage(
        contracts.MessageRole.ASSISTANT,
        "",
        tool_calls=(proposed,),
    )
    result = contracts.ChatResult(
        model_id="model-a",
        message=assistant_message,
    )
    tool_response = contracts.ProviderMessage(
        contracts.MessageRole.TOOL,
        "20 C",
        tool_call_id=proposed.call_id,
    )

    assert request.tools == (definition,)
    assert result.message.tool_calls == (proposed,)
    assert proposed.arguments_json == '{"city":"Paris"}'
    assert tool_response.tool_call_id == proposed.call_id
    assert "Paris" not in repr(proposed)


def test_tool_contracts_reject_malformed_names_ids_and_payloads():
    contracts = _contracts()
    schema = {"type": "object"}

    for invalid_name in ("", "bad name", "x" * 65):
        with pytest.raises(ValueError):
            contracts.ToolDefinition(name=invalid_name, input_schema=schema)
    with pytest.raises(ValueError):
        contracts.ToolDefinition(name="lookup", input_schema=[])
    with pytest.raises(ValueError):
        contracts.ToolDefinition(name="lookup", input_schema={"items": [object()]})
    with pytest.raises(ValueError):
        contracts.ToolDefinition(name="lookup", input_schema={"description": "x" * 65_537})

    valid_definition = contracts.ToolDefinition(name="lookup", input_schema=schema)
    numbered_provider_name = contracts.ToolDefinition(name="3.lookup", input_schema=schema)
    assert numbered_provider_name.name == "3.lookup"
    with pytest.raises(ValueError):
        contracts.ChatRequest(
            model_id="model-a",
            messages=(contracts.ProviderMessage(contracts.MessageRole.USER, "hello"),),
            tools=(valid_definition, valid_definition),
        )

    for invalid_id in ("", " call-1", "x" * 129):
        with pytest.raises(ValueError):
            contracts.ToolCall(
                call_id=invalid_id,
                name="lookup",
                arguments_json="{}",
            )
    for malformed_arguments in (
        "{not-json",
        "[]",
        "null",
        '{"value":"' + ("x" * 65_536) + '"}',
    ):
        with pytest.raises(ValueError):
            contracts.ToolCall(
                call_id="call-1",
                name="lookup",
                arguments_json=malformed_arguments,
            )

    valid_call = contracts.ToolCall(
        call_id="call-1",
        name="lookup",
        arguments_json="{}",
    )
    with pytest.raises(ValueError):
        contracts.ProviderMessage(
            contracts.MessageRole.ASSISTANT,
            "",
            tool_calls=(valid_call, valid_call),
        )
    with pytest.raises(ValueError):
        contracts.ProviderMessage(
            contracts.MessageRole.USER,
            "hello",
            tool_calls=(valid_call,),
        )


def test_stream_chunks_carry_partial_tool_call_deltas_without_executing_them():
    contracts = _contracts()
    first = contracts.ChatChunk(
        model_id="model-a",
        delta="",
        tool_call_deltas=(
            contracts.ToolCallDelta(
                index=0,
                name_fragment="lookup_",
                arguments_fragment='{"city"',
            ),
        ),
    )
    second = contracts.ChatChunk(
        model_id="model-a",
        delta="",
        tool_call_deltas=(
            contracts.ToolCallDelta(
                index=0,
                call_id="provider-call-1",
                name_fragment="weather",
                arguments_fragment=':"Paris"}',
            ),
        ),
    )

    assert first.tool_call_deltas[0].index == second.tool_call_deltas[0].index == 0
    assert first.tool_call_deltas[0].arguments_fragment == '{"city"'
    assert second.tool_call_deltas[0].call_id == "provider-call-1"
    assert second.tool_call_deltas[0].arguments_fragment == ':"Paris"}'

    with pytest.raises(ValueError):
        contracts.ToolCallDelta(index=-1, arguments_fragment="{}")
    with pytest.raises(ValueError):
        contracts.ToolCallDelta(index=0, call_id="bad id", arguments_fragment="{}")
    with pytest.raises(ValueError):
        contracts.ToolCallDelta(index=0, arguments_fragment="x" * 65_537)
    with pytest.raises(ValueError):
        contracts.ChatChunk(
            model_id="model-a",
            delta="",
            tool_call_deltas=(
                contracts.ToolCallDelta(index=0, arguments_fragment="{"),
                contracts.ToolCallDelta(index=0, arguments_fragment="}"),
            ),
        )


def test_capabilities_default_to_unknown():
    contracts = _contracts()

    capability = contracts.CapabilityValue()
    model = contracts.ModelCapabilities(
        provider_id=contracts.ProviderId.OLLAMA,
        model_id="installed-model",
    )

    assert capability.state is contracts.CapabilityState.UNKNOWN
    assert capability.source is contracts.CapabilityEvidenceSource.UNKNOWN
    assert model.tools.state is contracts.CapabilityState.UNKNOWN
    assert model.json_mode.state is contracts.CapabilityState.UNKNOWN
    assert model.vision.state is contracts.CapabilityState.UNKNOWN
    assert model.streaming.state is contracts.CapabilityState.UNKNOWN
    assert model.embeddings.state is contracts.CapabilityState.UNKNOWN
    assert model.tools.source is contracts.CapabilityEvidenceSource.UNKNOWN
    assert model.context_length_source is contracts.CapabilityEvidenceSource.UNKNOWN
    assert model.context_length is None


def test_provider_errors_normalize_without_leaking_internal_text():
    errors = _errors()
    internal_detail = "api_key=do-not-disclose"

    error = errors.normalize_provider_error(TimeoutError(internal_detail))

    assert error.code is errors.ProviderErrorCode.TIMEOUT
    assert internal_detail not in str(error)
    assert internal_detail not in error.safe_message


def test_health_result_carries_a_safe_error_category():
    contracts = _contracts()
    errors = _errors()

    result = contracts.HealthResult(
        available=False,
        error_code=errors.ProviderErrorCode.UNAVAILABLE,
    )

    assert result.error_code is errors.ProviderErrorCode.UNAVAILABLE


def test_registry_contains_only_approved_provider_definitions():
    contracts = _contracts()
    registry = _registry().ProviderRegistry()

    definitions = {item.provider_id: item for item in registry.definitions}

    assert set(definitions) == {
        contracts.ProviderId.OLLAMA,
        contracts.ProviderId.OPENAI_COMPATIBLE,
        contracts.ProviderId.LEGACY_GGUF,
        contracts.ProviderId.ANTHROPIC,
        contracts.ProviderId.GEMINI,
        contracts.ProviderId.SENTENCE_TRANSFORMERS,
    }
    assert definitions[contracts.ProviderId.SENTENCE_TRANSFORMERS].embedding_only is True


def test_adapter_protocol_declares_provider_operations():
    contracts = _contracts()

    assert {
        "list_models",
        "health_check",
        "get_capabilities",
        "chat",
        "stream_chat",
        "embed",
    } <= set(vars(contracts.ProviderAdapter))


def test_provider_package_import_is_lazy_and_has_no_network_or_credential_side_effects():
    script = r"""
import builtins
import socket
import sys

blocked_roots = {
    "ctypes",
    "cryptography",
    "httpx",
    "httpcore",
    "keyring",
    "llama_cpp",
    "sentence_transformers",
    "torch",
    "transformers",
    "win32cred",
    "win32crypt",
}
adapter_modules = {
    "backend.app.providers.ollama",
    "backend.app.providers.openai_compatible",
    "backend.app.providers.legacy_gguf",
    "backend.app.providers.anthropic",
    "backend.app.providers.gemini",
    "backend.app.providers.sentence_transformers",
}
real_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    root = name.partition(".")[0]
    if root in blocked_roots:
        raise AssertionError(f"unexpected eager import: {root}")
    return real_import(name, *args, **kwargs)

def denied_connect(*args, **kwargs):
    raise AssertionError("provider package import attempted network access")

builtins.__import__ = guarded_import
socket.socket.connect = denied_connect
socket.socket.connect_ex = denied_connect
socket.create_connection = denied_connect

import backend.app.providers

assert not (blocked_roots & {name.partition(".")[0] for name in sys.modules})
assert not (adapter_modules & set(sys.modules))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
