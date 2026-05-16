from __future__ import annotations

import asyncio
from html import escape
import json
import os
import time
from functools import lru_cache
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from languages import get_language
from logger import analytics_summary, log_event
from mcp_tools import registry


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    public_base_url: str = "https://moulcyber.duckdns.org"
    cors_allow_origins: str = "https://moulcyber.vercel.app,http://localhost:5173"
    cors_allow_origin_regex: str = r"https://.*\.vercel\.app"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    custom_llm_api_key: str | None = None
    llm_fallback_on_error: bool = True

    voice_provider: Literal["livekit", "elevenlabs"] = "livekit"
    livekit_sip_uri: str = "sip:0c0g2hzfv6c.sip.livekit.cloud;transport=tcp"
    livekit_agent_name: str = "moulcyber-live-agent"
    livekit_url: str | None = None
    livekit_api_key: str | None = None
    livekit_api_secret: str | None = None

    elevenlabs_api_key: str | None = None
    elevenlabs_agent_id: str | None = None
    elevenlabs_agent_phone_number_id: str | None = None

    twilio_phone_number: str = "+17754060061"
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_validate_signature: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
app = FastAPI(title="Moulcyber API", version="0.1.0")

origins = [origin.strip() for origin in settings.cors_allow_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["http://localhost:5173"],
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    language: str = "darija"
    topic: str | None = Field(default=None, max_length=80)


class ChatResponse(BaseModel):
    response: str
    language: str
    model: str
    grounded: bool
    sources: list[dict[str, str]] = []


class OutboundCallRequest(BaseModel):
    to_number: str = Field(..., min_length=8, max_length=32)
    language: str = "darija"


class OpenAIMessage(BaseModel):
    role: Literal["system", "developer", "user", "assistant", "tool", "function"]
    content: str | list[Any] | None = ""


class OpenAIChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[OpenAIMessage]
    temperature: float | None = 0.35
    max_tokens: int | None = 260
    stream: bool = False
    tools: list[dict[str, Any]] | None = None


def _extract_sources(response: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    try:
        candidates = getattr(response, "candidates", None) or []
        metadata = candidates[0].grounding_metadata if candidates else None
        chunks = getattr(metadata, "grounding_chunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None)
            title = getattr(web, "title", None)
            if uri:
                sources.append({"uri": uri, "title": title or uri})
    except (AttributeError, IndexError, TypeError):
        return sources
    return sources


def _gemini_generate_sync(
    *,
    prompt: str,
    system_instruction: str,
    temperature: float | None = 0.35,
    max_tokens: int | None = 260,
) -> tuple[str, list[dict[str, str]]]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=[grounding_tool],
        temperature=temperature if temperature is not None else 0.35,
        max_output_tokens=max(60, min(max_tokens or 260, 700)),
    )

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=config,
    )
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("Gemini returned an empty response")

    return text.strip(), _extract_sources(response)


def _gemini_answer_sync(message: str, language_code: str) -> tuple[str, list[dict[str, str]]]:
    language = get_language(language_code)
    return _gemini_generate_sync(prompt=message, system_instruction=language.system_prompt)


async def _gemini_answer(message: str, language_code: str) -> tuple[str, list[dict[str, str]]]:
    return await asyncio.to_thread(_gemini_answer_sync, message, language_code)


async def _gemini_generate(
    *,
    prompt: str,
    system_instruction: str,
    temperature: float | None = 0.35,
    max_tokens: int | None = 260,
) -> tuple[str, list[dict[str, str]]]:
    return await asyncio.to_thread(
        _gemini_generate_sync,
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def _twilio_client():
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required for outbound calls")

    from twilio.rest import Client

    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def _livekit_ready() -> bool:
    return bool(settings.livekit_sip_uri)


def _elevenlabs_ready() -> bool:
    return bool(settings.elevenlabs_api_key and settings.elevenlabs_agent_id)


def _calls_ready() -> bool:
    if settings.voice_provider == "livekit":
        return _livekit_ready()
    return _elevenlabs_ready()


def _request_url_for_twilio(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}{request.url.path}"
    return str(request.url)


def _validate_custom_llm_request(request: Request) -> None:
    if not settings.custom_llm_api_key:
        return

    secret = settings.custom_llm_api_key
    accepted_values = {secret, f"Bearer {secret}"}
    provided_values = {
        request.headers.get("authorization", ""),
        request.headers.get("x-api-key", ""),
        request.headers.get("api-key", ""),
        request.headers.get("x-custom-llm-key", ""),
    }
    if not accepted_values.intersection(provided_values):
        raise HTTPException(status_code=401, detail="Invalid custom LLM authorization")


async def _validate_twilio_request(request: Request, form_data: dict[str, Any]) -> None:
    if not settings.twilio_validate_signature:
        return
    if not settings.twilio_auth_token:
        raise HTTPException(status_code=500, detail="Twilio signature validation requires TWILIO_AUTH_TOKEN")

    from twilio.request_validator import RequestValidator

    signature = request.headers.get("x-twilio-signature")
    validator = RequestValidator(settings.twilio_auth_token)
    if not signature or not validator.validate(_request_url_for_twilio(request), form_data, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def _call_overrides(language_code: str, direction: str) -> dict[str, Any]:
    language = get_language(language_code)
    return {
        "type": "conversation_initiation_client_data",
        "dynamic_variables": {
            "language": language.code,
            "service_name": "Moulcyber",
            "call_direction": direction,
        },
        "conversation_config_override": {
            "agent": {
                "prompt": {"prompt": language.system_prompt},
                "first_message": language.first_message,
            }
        },
    }


async def _register_call(
    *,
    from_number: str,
    to_number: str,
    direction: str,
    language_code: str,
) -> str:
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")
    if not settings.elevenlabs_agent_id:
        raise RuntimeError("ELEVENLABS_AGENT_ID is not configured")

    import httpx

    payload = {
        "agent_id": settings.elevenlabs_agent_id,
        "from_number": from_number,
        "to_number": to_number,
        "direction": direction,
        "conversation_initiation_client_data": _call_overrides(language_code, direction),
    }
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json, application/xml, text/xml, text/plain",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.elevenlabs.io/v1/convai/twilio/register-call",
            json=payload,
            headers=headers,
        )

    response.raise_for_status()
    try:
        parsed = response.json()
    except ValueError:
        parsed = response.text

    if isinstance(parsed, str):
        return parsed
    return response.text


def _livekit_sip_twiml() -> str:
    if not settings.livekit_sip_uri:
        raise RuntimeError("LIVEKIT_SIP_URI is required when VOICE_PROVIDER=livekit")

    sip_uri = escape(settings.livekit_sip_uri, quote=False)
    return (
        '<Response><Dial answerOnBridge="true">'
        f"<Sip>{sip_uri}</Sip>"
        "</Dial></Response>"
    )


async def _call_bridge_twiml(
    *,
    from_number: str,
    to_number: str,
    direction: str,
    language_code: str,
) -> tuple[str, str]:
    if settings.voice_provider == "livekit":
        return _livekit_sip_twiml(), "livekit"

    twiml = await _register_call(
        from_number=from_number,
        to_number=to_number,
        direction=direction,
        language_code=language_code,
    )
    return twiml, "elevenlabs"


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "moulcyber",
        "twilio_number": settings.twilio_phone_number,
        "voice_provider": settings.voice_provider,
        "calls_ready": _calls_ready(),
        "livekit_ready": _livekit_ready(),
        "livekit_agent": settings.livekit_agent_name,
        "elevenlabs_fallback_ready": _elevenlabs_ready(),
        "chat_ready": bool(settings.gemini_api_key),
        "custom_llm_ready": bool(settings.gemini_api_key),
        "llm_fallback_on_error": settings.llm_fallback_on_error,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    language = get_language(payload.language)
    topic = payload.topic or payload.message[:80]

    try:
        answer, sources = await _gemini_answer(payload.message, language.code)
    except Exception as exc:
        await log_event(topic=topic, language=language.code, success=False, response_text=None)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await log_event(topic=topic, language=language.code, success=True, response_text=answer)
    return ChatResponse(
        response=answer,
        language=language.code,
        model=settings.gemini_model,
        grounded=bool(sources),
        sources=sources,
    )


@app.get("/api/analytics")
async def analytics() -> dict[str, Any]:
    return await analytics_summary()


@app.get("/api/mcp-tools")
async def mcp_tools() -> dict[str, Any]:
    return {"tools": registry.list_tools()}


def _message_text(content: str | list[Any] | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _build_custom_llm_prompt(messages: list[OpenAIMessage]) -> tuple[str, str]:
    system_parts: list[str] = []
    transcript_parts: list[str] = []

    for message in messages:
        text = _message_text(message.content).strip()
        if not text:
            continue
        if message.role in {"system", "developer"}:
            system_parts.append(text)
        else:
            transcript_parts.append(f"{message.role}: {text}")

    system_instruction = "\n\n".join(system_parts).strip() or get_language("darija").system_prompt
    transcript = "\n".join(transcript_parts).strip()
    if not transcript:
        transcript = "user: Salam, bghit nswlek."
    return system_instruction, transcript


def _chat_completion_payload(answer: str, model: str) -> dict[str, Any]:
    return {
        "id": f"chatcmpl-moulcyber-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": len(answer.split()),
            "total_tokens": len(answer.split()),
        },
    }


def _custom_llm_fallback(exc: Exception) -> str:
    detail = str(exc)
    if "429" in detail or "RESOURCE_EXHAUSTED" in detail:
        return (
            "Smah liya khouya, service d l-internet daba wa9ef 3la quota. "
            "3awed lia chwiya mn b3d, w njawebk b-Darija mzyana."
        )
    return (
        "Smah liya khouya, l-khadma d l-internet ma jawbatch daba. "
        "3awed lia soual b tariqa okhra."
    )


async def _stream_chat_completion(answer: str, model: str):
    completion_id = f"chatcmpl-moulcyber-{int(time.time() * 1000)}"
    created = int(time.time())
    chunks = [
        {"role": "assistant"},
        {"content": answer},
    ]
    for delta in chunks:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    done = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def custom_llm_chat_completions(request: Request, payload: OpenAIChatCompletionRequest):
    _validate_custom_llm_request(request)
    system_instruction, prompt = _build_custom_llm_prompt(payload.messages)

    try:
        answer, _sources = await _gemini_generate(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
        )
    except Exception as exc:
        if not settings.llm_fallback_on_error:
            await log_event(topic="custom_llm_chat", language="darija", success=False)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        answer = _custom_llm_fallback(exc)
        await log_event(topic="custom_llm_chat", language="darija", success=False, response_text=answer)
    else:
        await log_event(topic="custom_llm_chat", language="darija", success=True, response_text=answer)


    model = payload.model or settings.gemini_model
    if payload.stream:
        return StreamingResponse(
            _stream_chat_completion(answer, model),
            media_type="text/event-stream",
        )
    return _chat_completion_payload(answer, model)


@app.post("/twilio/inbound")
async def twilio_inbound(request: Request) -> Response:
    form = await request.form()
    form_data = dict(form)
    await _validate_twilio_request(request, form_data)

    from_number = str(form_data.get("From") or "")
    to_number = str(form_data.get("To") or settings.twilio_phone_number)
    language_code = str(form_data.get("Language") or "darija")

    try:
        twiml, provider = await _call_bridge_twiml(
            from_number=from_number,
            to_number=to_number,
            direction="inbound",
            language_code=language_code,
        )
        await log_event(
            topic="twilio_inbound_call",
            language=get_language(language_code).code,
            success=True,
            metadata={"direction": "inbound", "provider": provider},
        )
        return Response(content=twiml, media_type="application/xml")
    except Exception as exc:
        await log_event(topic="twilio_inbound_call", language="darija", success=False)
        fallback = (
            "<Response><Say language=\"fr-FR\">"
            "Le service Moulcyber n'est pas configure pour le moment."
            "</Say></Response>"
        )
        if settings.app_env == "production":
            return Response(content=fallback, media_type="application/xml", status_code=200)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/twilio/outbound")
async def twilio_outbound(request: Request) -> Response:
    form = await request.form()
    form_data = dict(form)
    await _validate_twilio_request(request, form_data)

    from_number = str(form_data.get("From") or settings.twilio_phone_number)
    to_number = str(form_data.get("To") or "")
    language_code = str(form_data.get("Language") or "darija")

    try:
        twiml, provider = await _call_bridge_twiml(
            from_number=from_number,
            to_number=to_number,
            direction="outbound",
            language_code=language_code,
        )
        await log_event(
            topic="twilio_outbound_bridge",
            language=get_language(language_code).code,
            success=True,
            metadata={"direction": "outbound", "provider": provider},
        )
        return Response(content=twiml, media_type="application/xml")
    except Exception as exc:
        await log_event(topic="twilio_outbound_bridge", language="darija", success=False)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/calls/outbound")
async def start_outbound_call(payload: OutboundCallRequest) -> dict[str, Any]:
    url = f"{settings.public_base_url.rstrip('/')}/twilio/outbound"
    status_callback = f"{settings.public_base_url.rstrip('/')}/twilio/status"

    try:
        client = _twilio_client()
        call = await asyncio.to_thread(
            client.calls.create,
            to=payload.to_number,
            from_=settings.twilio_phone_number,
            url=url,
            method="POST",
            status_callback=status_callback,
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )
    except Exception as exc:
        await log_event(topic="twilio_start_outbound", language=payload.language, success=False)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    await log_event(
        topic="twilio_start_outbound",
        language=get_language(payload.language).code,
        success=True,
        metadata={"direction": "outbound", "provider": "twilio"},
    )
    return {"success": True, "call_sid": call.sid, "to_number": payload.to_number}


@app.post("/twilio/status")
async def twilio_status(request: Request) -> dict[str, Any]:
    form = await request.form()
    form_data = dict(form)
    await _validate_twilio_request(request, form_data)

    await log_event(
        topic="twilio_call_status",
        language="darija",
        success=True,
        metadata={
            "direction": str(form_data.get("Direction") or ""),
            "call_status": str(form_data.get("CallStatus") or ""),
            "provider": "twilio",
        },
    )
    return {"received": True}
