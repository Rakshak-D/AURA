"""Authenticated Settings APIs for A1-G provider connections and model roles."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, StrictStr
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models.sql_models import User
from ..providers.errors import ProviderError, ProviderErrorCode
from ..providers.service import FUNCTIONAL_PROVIDER_TYPES, ProviderService, get_provider_service

router = APIRouter(prefix="/settings/models", tags=["model settings"])


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class ConnectionCreate(StrictInput):
    name: StrictStr = Field(min_length=1, max_length=100)
    provider_type: Literal["ollama", "openai_compatible"]
    base_url: StrictStr | None = Field(default=None, max_length=2048)
    token_limit_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class ConnectionPatch(StrictInput):
    name: StrictStr | None = Field(default=None, min_length=1, max_length=100)
    base_url: StrictStr | None = Field(default=None, min_length=1, max_length=2048)
    token_limit_parameter: Literal["max_tokens", "max_completion_tokens"] | None = None


class CredentialInput(StrictInput):
    api_key: SecretStr = Field(min_length=1, max_length=8192)


class RoleInput(StrictInput):
    connection_id: StrictStr = Field(min_length=1, max_length=64)
    model_id: StrictStr = Field(min_length=1, max_length=512)


class LocalOnlyInput(StrictInput):
    enabled: StrictBool


def _lookup_http_error(_error: LookupError) -> HTTPException:
    return HTTPException(status_code=404, detail="Provider connection not found.")


def _provider_http_error(error: ProviderError) -> HTTPException:
    status = 403 if error.code is ProviderErrorCode.LOCAL_ONLY_BLOCKED else 502
    if error.code in {ProviderErrorCode.INCOMPLETE_CONFIGURATION, ProviderErrorCode.UNSUPPORTED_CAPABILITY}:
        status = 400
    if error.code is ProviderErrorCode.CONNECTION_REMOVED:
        status = 410
    return HTTPException(
        status_code=status,
        detail=error.safe_message,
        headers={"X-AURA-Provider-Error": error.code.value},
    )


def _translate_call(callback, *args, **kwargs):
    try:
        return callback(*args, **kwargs)
    except LookupError as error:
        raise _lookup_http_error(error) from None
    except ProviderError as error:
        raise _provider_http_error(error) from None
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from None


@router.get("")
def get_model_settings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    return service.snapshot(db, user.id)


@router.get("/provider-types")
def get_provider_types(user: User = Depends(get_current_user)):
    return {
        "providers": [
            {
                "id": provider.value,
                "name": "Ollama" if provider.value == "ollama" else "OpenAI-compatible",
                "available": True,
            }
            for provider in FUNCTIONAL_PROVIDER_TYPES
        ]
    }


@router.post("/connections", status_code=201)
def create_connection(
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    return _translate_call(
        service.create_connection,
        db,
        user.id,
        name=payload.name,
        provider_type=payload.provider_type,
        base_url=payload.base_url,
        token_limit_parameter=payload.token_limit_parameter,
    )


@router.patch("/connections/{connection_id}")
def update_connection(
    connection_id: str,
    payload: ConnectionPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    return _translate_call(
        service.update_connection,
        db,
        user.id,
        connection_id,
        **payload.model_dump(exclude_unset=True),
    )


@router.delete("/connections/{connection_id}")
def delete_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    _translate_call(service.remove_connection, db, user.id, connection_id)
    return {"removed": True, "connection_id": connection_id}


@router.put("/connections/{connection_id}/credential")
def put_connection_credential(
    connection_id: str,
    payload: CredentialInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    from ..providers.contracts import EphemeralCredential

    credential = EphemeralCredential(payload.api_key.get_secret_value())
    _translate_call(service.set_credential, db, user.id, connection_id, credential)
    return {"has_api_key": True}


@router.delete("/connections/{connection_id}/credential")
def delete_connection_credential(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    configured = _translate_call(service.delete_credential, db, user.id, connection_id)
    return {"has_api_key": configured}


@router.get("/connections/{connection_id}/models")
async def list_connection_models(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    try:
        models = await service.list_models(db, user.id, connection_id)
    except LookupError as error:
        raise _lookup_http_error(error) from None
    except ProviderError as error:
        raise _provider_http_error(error) from None
    return {"models": models, "verified": True}


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    try:
        return await service.test_connection(db, user.id, connection_id)
    except LookupError as error:
        raise _lookup_http_error(error) from None
    except ProviderError as error:
        raise _provider_http_error(error) from None


@router.get("/connections/{connection_id}/models/{model_id:path}/capabilities")
async def get_model_capabilities(
    connection_id: str,
    model_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    try:
        return await service.capabilities(db, user.id, connection_id, model_id)
    except LookupError as error:
        raise _lookup_http_error(error) from None
    except ProviderError as error:
        raise _provider_http_error(error) from None


@router.put("/roles/{role}")
def put_role_selection(
    role: str,
    payload: RoleInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    return _translate_call(
        service.save_role,
        db,
        user.id,
        role,
        payload.connection_id,
        payload.model_id,
    )


@router.delete("/roles/{role}")
def delete_role_selection(
    role: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    deleted = _translate_call(service.clear_role, db, user.id, role)
    return {"deleted": deleted, "role": role}


@router.put("/local-only")
def put_local_only(
    payload: LocalOnlyInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    service: ProviderService = Depends(get_provider_service),
):
    return {"local_only": service.set_local_only(db, user.id, payload.enabled)}
