import asyncio
import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from ..database import get_db, utc_now
from ..auth import get_current_user_id
from ..models.sql_models import ChatHistory
from ..models.pydantic_models import ChatMessage, ChatResponse
from ..services.chat_service import process_chat
from ..services.chat_service import chat_service
from ..providers.contracts import SuccessfulChatFinishReason
from ..providers.errors import ProviderError, ProviderErrorCode, normalize_provider_error
from ..providers.service import ProviderService, get_provider_service
from ..utils.security import sanitize_input, limiter
from ..utils.responses import success_response

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("5/minute")
async def chat_endpoint(request: Request, msg: ChatMessage, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id), provider_service: ProviderService = Depends(get_provider_service)):
    """
    Primary chat endpoint. Persists the raw user message and then delegates
    to the ChatService, which handles tool routing and RAG.
    """
    # Note: Request object is needed for slowapi
    try:
        user_id = current_user_id
        # Sanitize input
        user_message = sanitize_input(msg.message)

        sanitized_message = ChatMessage(message=user_message, context={})
        result = await process_chat(user_id, sanitized_message, db, provider_service)

        return result

    except HTTPException:
        # Let explicit HTTP errors bubble up
        raise
    except Exception:
        logger = logging.getLogger(__name__)
        logger.error("Chat endpoint failed")
        raise HTTPException(status_code=500, detail="Internal server error")


_STREAM_MAX_MESSAGE_BYTES = 16_384
_STREAM_MAX_OUTPUT_BYTES = 1_048_576
_STREAM_DELTA_BYTES = 4_096
_NO_MODEL_MESSAGE = "No AI model is available right now, so I can't answer general chat messages."


def _sse(event_name: str, payload: dict[str, object]) -> bytes:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_name}\ndata: {encoded}\n\n".encode("utf-8")


def _bounded_text_parts(value: str):
    pending = ""
    pending_bytes = 0
    for character in value:
        size = len(character.encode("utf-8"))
        if pending and pending_bytes + size > _STREAM_DELTA_BYTES:
            yield pending
            pending = ""
            pending_bytes = 0
        pending += character
        pending_bytes += size
    if pending:
        yield pending


@router.post("/chat/stream")
@limiter.limit("5/minute")
async def stream_chat_endpoint(
    request: Request,
    msg: ChatMessage,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
    provider_service: ProviderService = Depends(get_provider_service),
):
    """Authenticated fetch-readable SSE stream for the explicitly selected Chat role."""
    message = sanitize_input(msg.message)
    if not message or len(message.encode("utf-8")) > _STREAM_MAX_MESSAGE_BYTES:
        raise HTTPException(status_code=413, detail="Chat message is empty or too large.")

    db.add(
        ChatHistory(
            user_id=current_user_id,
            role="user",
            content=message,
            timestamp=utc_now(),
        )
    )
    db.commit()

    request_id = uuid4().hex
    resolved = None
    routed_result = None
    preflight_error: ProviderError | None = None
    try:
        selection = provider_service.chat_role(db, current_user_id)
        routed_result = await chat_service.process_pre_provider_actions(
            current_user_id, message, db, selection is not None
        )
        if routed_result is not None:
            db.rollback()
        else:
            resolved = provider_service.resolve_chat(db, current_user_id)
    except ProviderError as error:
        preflight_error = error
    except LookupError:
        preflight_error = ProviderError(ProviderErrorCode.CONNECTION_REMOVED)
    except Exception:
        preflight_error = ProviderError(ProviderErrorCode.UNAVAILABLE)
    finally:
        # Do not keep a database transaction open during provider generation.
        db.rollback()

    async def event_stream():
        started: dict[str, object] = {"request_id": request_id}
        if resolved is not None:
            started.update(
                {
                    "model_id": resolved["model_id"],
                    "provider_type": resolved["provider_type"],
                    "connection_name": resolved["connection_name"],
                    "locality": resolved["locality"],
                }
            )
        yield _sse("started", started)

        if routed_result is not None:
            response_text = str(routed_result.get("response", ""))
            for part in _bounded_text_parts(response_text):
                yield _sse(
                    "text_delta",
                    {"request_id": request_id, "delta": part},
                )
            yield _sse(
                "completed",
                {
                    "request_id": request_id,
                    "action_taken": routed_result.get("action_taken"),
                    "data": routed_result.get("data", {}),
                    "suggestions": routed_result.get("suggestions", []),
                },
            )
            return

        if preflight_error is not None:
            yield _sse(
                "failed",
                {
                    "request_id": request_id,
                    "code": preflight_error.code.value,
                    "message": preflight_error.safe_message,
                    "incomplete": False,
                },
            )
            return
        if resolved is None:
            chat_service.save_message(
                current_user_id, "assistant", _NO_MODEL_MESSAGE, db, intent="general_chat"
            )
            yield _sse(
                "failed",
                {
                    "request_id": request_id,
                    "code": "no_model_available",
                    "message": _NO_MODEL_MESSAGE,
                    "incomplete": False,
                },
            )
            return

        request_value = provider_service.chat_request(resolved["model_id"], message)
        provider_stream = resolved["adapter"].stream_chat(
            resolved["context"], request_value
        )
        output: list[str] = []
        output_bytes = 0
        terminal_seen = False
        try:
            async for chunk in provider_stream:
                if terminal_seen or chunk.model_id != resolved["model_id"]:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                if chunk.tool_call_deltas:
                    # A1-G never executes or publishes provider-proposed tools.
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                if chunk.delta:
                    size = len(chunk.delta.encode("utf-8"))
                    if output_bytes + size > _STREAM_MAX_OUTPUT_BYTES:
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    output_bytes += size
                    output.append(chunk.delta)
                    for part in _bounded_text_parts(chunk.delta):
                        yield _sse(
                            "text_delta",
                            {"request_id": request_id, "delta": part},
                        )
                if chunk.finish_reason is not None:
                    try:
                        finish_reason = SuccessfulChatFinishReason(chunk.finish_reason)
                    except (TypeError, ValueError):
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
                    if finish_reason is not SuccessfulChatFinishReason.STOP:
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    terminal_seen = True
            if not terminal_seen or not output:
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)

            completed_text = "".join(output)
            db.add(
                ChatHistory(
                    user_id=current_user_id,
                    role="assistant",
                    content=completed_text,
                    intent="general_chat",
                    timestamp=utc_now(),
                )
            )
            db.commit()
            yield _sse(
                "completed",
                {
                    "request_id": request_id,
                    "model_id": resolved["model_id"],
                    "provider_type": resolved["provider_type"],
                    "connection_name": resolved["connection_name"],
                    "locality": resolved["locality"],
                },
            )
        except asyncio.CancelledError:
            db.rollback()
            raise
        except ProviderError as error:
            db.rollback()
            yield _sse(
                "failed",
                {
                    "request_id": request_id,
                    "code": error.code.value,
                    "message": error.safe_message,
                    "incomplete": bool(output),
                },
            )
        except Exception as error:
            db.rollback()
            safe_error = normalize_provider_error(error)
            logging.getLogger(__name__).warning(
                "Provider stream failed with normalized category %s (%s)",
                safe_error.code.value,
                type(error).__name__,
            )
            yield _sse(
                "failed",
                {
                    "request_id": request_id,
                    "code": safe_error.code.value,
                    "message": safe_error.safe_message,
                    "incomplete": bool(output),
                },
            )
        finally:
            close = getattr(provider_stream, "aclose", None)
            if close is not None:
                await close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )


@router.delete("/chat/history")
async def clear_chat_history(db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id)):
    """
    Clear all stored chat history for the default user.
    """
    try:
        user_id = current_user_id
        deleted = db.query(ChatHistory).filter(ChatHistory.user_id == user_id).delete()
        db.commit()
        return success_response(data={"deleted": deleted}, message="Chat history cleared.")
    except Exception as e:
        db.rollback()
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error clearing chat history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear chat history")
