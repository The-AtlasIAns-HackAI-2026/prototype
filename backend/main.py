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

from hotline_engine import (
    confirm_oral_approval,
    load_experts,
    read_mock_submissions,
    route_issue,
    start_oral_approval,
    submit_mock_chikaya,
)
from languages import get_language
from legal_rag import build_legal_answer_prompt, legal_rag_status, retrieve_legal_context
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
    hotline_experts_file: str = "/app/config/hotline/experts.json"
    mock_chikaya_log_file: str = "/app/logs/mock_chikaya_submissions.jsonl"
    oral_approval_log_file: str = "/app/logs/oral_approvals.jsonl"
    legal_rag_dir: str = "/app/rag_datasets"

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
app = FastAPI(title="Khadamati API", version="0.1.0")
LEGAL_RAG_SECTORS = {
    "family_law",
    "criminal_law",
    "civil_procedure",
    "constitutional_law",
    "public_finance",
}

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


class HotlineTriageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=3000)
    language: str = "darija"
    city: str | None = Field(default=None, max_length=120)
    provided_fields: dict[str, Any] = Field(default_factory=dict)
    channel: str = Field(default="web", max_length=40)
    call_id: str | None = Field(default=None, max_length=120)
    caller_phone: str | None = Field(default=None, max_length=40)
    trace_id: str | None = Field(default=None, max_length=120)


class MockChikayaSubmissionRequest(BaseModel):
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    topic: str | None = Field(default=None, max_length=1000)
    citizen_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    caller_phone: str | None = Field(default=None, max_length=40)
    city: str = Field(default="not provided", max_length=120)
    category: str = Field(default="legal or administrative complaint", max_length=120)
    subject: str | None = Field(default=None, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    desired_resolution: str | None = Field(default=None, max_length=1000)
    evidence: list[str] = Field(default_factory=list, max_length=12)
    consent: bool = False
    source: Literal["mock-website", "voice-agent", "api"] = "api"
    channel: str = Field(default="web", max_length=40)
    call_id: str | None = Field(default=None, max_length=120)
    trace_id: str | None = Field(default=None, max_length=120)


class LegalRAGRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=3000)
    language: str = "darija"
    sector: str | None = Field(default=None, max_length=80)
    top_k: int = Field(default=4, ge=1, le=8)
    use_llm: bool = True
    merge_related_sectors: bool = True
    channel: str = Field(default="web", max_length=40)
    call_id: str | None = Field(default=None, max_length=120)
    caller_phone: str | None = Field(default=None, max_length=40)
    trace_id: str | None = Field(default=None, max_length=120)


class CasePacketRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=3000)
    language: str = "darija"
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    merge_related_sectors: bool = True
    channel: str = Field(default="web", max_length=40)
    call_id: str | None = Field(default=None, max_length=120)
    caller_phone: str | None = Field(default=None, max_length=40)
    trace_id: str | None = Field(default=None, max_length=120)


class OralApprovalStartRequest(BaseModel):
    action: str = Field(..., min_length=2, max_length=120)
    summary: str = Field(..., min_length=4, max_length=1000)
    channel: str = Field(default="web", max_length=40)
    call_id: str | None = Field(default=None, max_length=120)
    caller_phone: str | None = Field(default=None, max_length=40)
    trace_id: str | None = Field(default=None, max_length=120)


class OralApprovalConfirmRequest(BaseModel):
    approval_id: str = Field(..., min_length=4, max_length=80)
    spoken_text: str = Field(..., min_length=1, max_length=500)
    channel: str = Field(default="web", max_length=40)
    call_id: str | None = Field(default=None, max_length=120)
    caller_phone: str | None = Field(default=None, max_length=40)
    trace_id: str | None = Field(default=None, max_length=120)


class CallEventRequest(BaseModel):
    event_type: str = Field(..., min_length=2, max_length=100)
    channel: str = Field(default="voice-agent", max_length=40)
    call_id: str | None = Field(default=None, max_length=120)
    caller_phone: str | None = Field(default=None, max_length=40)
    trace_id: str | None = Field(default=None, max_length=120)
    room_name: str | None = Field(default=None, max_length=160)
    participant_identity: str | None = Field(default=None, max_length=160)
    tool: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=100)
    article: str | None = Field(default=None, max_length=100)
    latency_ms: float | None = None
    success: bool = True


class MCPToolRunRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


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
    grounding: bool = True,
) -> tuple[str, list[dict[str, str]]]:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)
    tools = [types.Tool(google_search=types.GoogleSearch())] if grounding else None
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=tools,
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
    grounding: bool = True,
) -> tuple[str, list[dict[str, str]]]:
    return await asyncio.to_thread(
        _gemini_generate_sync,
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=temperature,
        max_tokens=max_tokens,
        grounding=grounding,
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


def _event_metadata(payload: Any | None = None, **extra: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if payload is not None:
        for key in ("channel", "call_id", "caller_phone", "trace_id", "source"):
            value = getattr(payload, key, None)
            if value:
                metadata[key] = value
    metadata.update({key: value for key, value in extra.items() if value not in (None, "")})
    return metadata


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
            "service_name": "Khadamati",
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
        "service": "khadamati",
        "twilio_number": settings.twilio_phone_number,
        "voice_provider": settings.voice_provider,
        "calls_ready": _calls_ready(),
        "livekit_ready": _livekit_ready(),
        "livekit_agent": settings.livekit_agent_name,
        "elevenlabs_fallback_ready": _elevenlabs_ready(),
        "hotline_ready": True,
        "legal_rag_ready": True,
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


@app.post("/api/mcp-tools/{tool_name}/run")
async def run_mcp_tool(tool_name: str, request: MCPToolRunRequest) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = await registry.run(tool_name, request.payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        await log_event(
            topic=f"mcp_tool:{tool_name}",
            language=str(request.payload.get("language") or "darija"),
            success=False,
            metadata=_event_metadata(
                None,
                channel=str(request.payload.get("channel") or request.payload.get("source") or "api"),
                call_id=request.payload.get("call_id"),
                caller_phone=request.payload.get("caller_phone") or request.payload.get("phone"),
                trace_id=request.payload.get("trace_id"),
                tool=tool_name,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            ),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await log_event(
        topic=f"mcp_tool:{tool_name}",
        language=str(request.payload.get("language") or "darija"),
        success=True,
        response_text=str(result.get("answer") or result.get("receipt_id") or result.get("status") or ""),
        metadata=_event_metadata(
            None,
            channel=str(request.payload.get("channel") or request.payload.get("source") or "api"),
            call_id=request.payload.get("call_id"),
            caller_phone=request.payload.get("caller_phone") or request.payload.get("phone"),
            trace_id=request.payload.get("trace_id"),
            tool=tool_name,
            route=(result.get("route") or {}).get("sector") if isinstance(result.get("route"), dict) else None,
            agent_id=(result.get("route") or {}).get("agent_id") if isinstance(result.get("route"), dict) else None,
            workflow=result.get("merge_strategy"),
            article=((result.get("results") or [{}])[0] or {}).get("primary_article")
            if isinstance(result.get("results"), list)
            else result.get("primary_article"),
            receipt_id=result.get("receipt_id"),
            approval_id=result.get("approval_id"),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        ),
    )
    return result


@app.post("/api/call-events")
async def call_event(payload: CallEventRequest) -> dict[str, Any]:
    event = await log_event(
        topic=f"call:{payload.event_type}",
        language="darija",
        success=payload.success,
        metadata=_event_metadata(
            payload,
            tool=payload.tool,
            route=payload.route,
            article=payload.article,
            room_name=payload.room_name,
            participant_identity=payload.participant_identity,
            latency_ms=payload.latency_ms,
        ),
    )
    return {"logged": True, "event": event}


@app.get("/api/hotline/experts")
async def hotline_experts() -> dict[str, Any]:
    experts = [expert.public_dict() for expert in load_experts()]
    return {"experts": experts, "count": len(experts)}


@app.post("/api/hotline/triage")
async def hotline_triage(payload: HotlineTriageRequest) -> dict[str, Any]:
    provided = dict(payload.provided_fields)
    if payload.city and not provided.get("city"):
        provided["city"] = payload.city

    result = route_issue(
        message=payload.message,
        language=get_language(payload.language).code,
        provided_fields=provided,
    )
    await log_event(
        topic="hotline_triage",
        language=get_language(payload.language).code,
        success=True,
        response_text=result["recommended_action"],
        metadata=_event_metadata(
            payload,
            tool="hotline_route_issue",
            route=result.get("selected_expert", {}).get("id"),
        ),
    )
    return result


@app.post("/api/hotline/chikaya/mock-submit")
async def mock_chikaya_submit(payload: MockChikayaSubmissionRequest) -> dict[str, Any]:
    result = await submit_mock_chikaya(payload.model_dump())
    await log_event(
        topic="mock_chikaya_submit",
        language="darija",
        success=bool(result.get("submitted")),
        response_text=str(result.get("receipt_id") or result.get("missing_fields") or ""),
        metadata=_event_metadata(
            payload,
            tool="mock_chikaya_submit",
            receipt_id=result.get("receipt_id"),
        ),
    )
    return result


@app.get("/api/hotline/chikaya/mock-submissions")
async def mock_chikaya_submissions(limit: int = 20) -> dict[str, Any]:
    capped_limit = max(1, min(limit, 100))
    submissions = await read_mock_submissions(capped_limit)
    return {"submissions": submissions, "count": len(submissions)}


@app.post("/api/hotline/approval/start")
async def oral_approval_start(payload: OralApprovalStartRequest) -> dict[str, Any]:
    result = await start_oral_approval(payload.model_dump())
    await log_event(
        topic="oral_approval_start",
        language="darija",
        success=True,
        response_text=result.get("approval_id"),
        metadata=_event_metadata(
            payload,
            tool="approval_flow_start",
            approval_id=result.get("approval_id"),
        ),
    )
    return result


@app.post("/api/hotline/approval/confirm")
async def oral_approval_confirm(payload: OralApprovalConfirmRequest) -> dict[str, Any]:
    result = await confirm_oral_approval(payload.model_dump())
    await log_event(
        topic="oral_approval_confirm",
        language="darija",
        success=bool(result.get("approved")),
        response_text=result.get("status"),
        metadata=_event_metadata(
            payload,
            tool="approval_flow_confirm",
            approval_id=result.get("approval_id"),
        ),
    )
    return result


@app.get("/api/legal-rag/status")
async def legal_rag_status_endpoint() -> dict[str, Any]:
    return legal_rag_status()


@app.post("/api/legal-rag/query")
async def legal_rag_query(payload: LegalRAGRequest) -> dict[str, Any]:
    started = time.perf_counter()
    retrieval = retrieve_legal_context(
        question=payload.question,
        sector=payload.sector,
        top_k=payload.top_k,
        merge_related_sectors=payload.merge_related_sectors,
    )

    answer = ""
    generation_ms = 0.0
    answer_model = "retrieval_only"
    if payload.use_llm:
        system_instruction, prompt = build_legal_answer_prompt(payload.question, retrieval)
        generation_started = time.perf_counter()
        try:
            answer, _sources = await _gemini_generate(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=0.2,
                max_tokens=320,
                grounding=False,
            )
            answer_model = settings.gemini_model
        except Exception as exc:
            answer = _fallback_rag_answer(payload.question, retrieval, exc)
            answer_model = "retrieval_fallback"
        generation_ms = (time.perf_counter() - generation_started) * 1000
    else:
        answer = _local_rag_answer(retrieval)
        answer_model = "local_extractive_rag"

    total_ms = (time.perf_counter() - started) * 1000
    result = {
        **retrieval,
        "answer": answer,
        "answer_model": answer_model,
        "generation_ms": round(generation_ms, 2),
        "latency_ms": round(total_ms, 2),
        "low_latency_mode": not payload.use_llm,
    }
    await log_event(
        topic="legal_rag_query",
        language=get_language(payload.language).code,
        success=True,
        response_text=answer or payload.question,
        metadata=_event_metadata(
            payload,
            provider=answer_model,
            tool="legal_rag_retrieve",
            route=(retrieval.get("route") or {}).get("sector"),
            agent_id=(retrieval.get("route") or {}).get("agent_id"),
            workflow=retrieval.get("merge_strategy"),
            article=((retrieval.get("results") or [{}])[0] or {}).get("primary_article"),
            latency_ms=round(total_ms, 2),
        ),
    )
    return result


@app.post("/api/hotline/case-packet")
async def case_packet(payload: CasePacketRequest) -> dict[str, Any]:
    started = time.perf_counter()
    provided = {
        "city": payload.city,
        "first_name": payload.first_name,
        "last_name": payload.last_name,
        "caller_phone": payload.caller_phone,
        "topic": payload.topic,
    }
    triage = route_issue(
        message=payload.topic,
        language=get_language(payload.language).code,
        provided_fields={key: value for key, value in provided.items() if value},
    )
    selected_expert_id = (triage.get("selected_expert") or {}).get("id")
    retrieval = retrieve_legal_context(
        question=payload.topic,
        sector=selected_expert_id if selected_expert_id in LEGAL_RAG_SECTORS else None,
        merge_related_sectors=payload.merge_related_sectors,
        top_k=3,
    )
    first_source = (retrieval.get("results") or [{}])[0]
    packet = {
        "packet_id": f"KHD-PACKET-{int(time.time() * 1000)}",
        "citizen": {
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "caller_phone": payload.caller_phone,
            "city": payload.city,
        },
        "topic": payload.topic,
        "workflow": {
            "channel": payload.channel,
            "call_id": payload.call_id,
            "master_agent": "khadamati_legal_master",
            "selected_expert": triage.get("selected_expert"),
            "rag_route": retrieval.get("route"),
            "merged_routes": retrieval.get("merged_routes"),
            "intervening_agents": retrieval.get("intervening_agents"),
            "merge_strategy": retrieval.get("merge_strategy"),
            "a2a_trace": retrieval.get("a2a_trace"),
        },
        "legal_anchor": {
            "primary_article": first_source.get("primary_article"),
            "article_count": first_source.get("article_count"),
            "chunk_id": first_source.get("chunk_id"),
            "pages": [first_source.get("page_start"), first_source.get("page_end")],
        },
        "knowledge_graph": retrieval.get("knowledge_graph"),
        "intake": {
            "missing_fields": triage.get("missing_fields", []),
            "next_questions": triage.get("next_questions", []),
            "evidence_checklist": triage.get("evidence_checklist", []),
            "risk_flags": triage.get("risk_flags", []),
            "recommended_action": triage.get("recommended_action"),
        },
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    await log_event(
        topic="case_packet_build",
        language=get_language(payload.language).code,
        success=True,
        response_text=payload.topic,
        metadata=_event_metadata(
            payload,
            tool="case_packet_build",
            route=(retrieval.get("route") or {}).get("sector"),
            agent_id=(retrieval.get("route") or {}).get("agent_id"),
            workflow=retrieval.get("merge_strategy"),
            article=first_source.get("primary_article"),
            latency_ms=packet["latency_ms"],
        ),
    )
    return packet


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
        "id": f"chatcmpl-khadamati-{int(time.time() * 1000)}",
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


def _fallback_rag_answer(question: str, retrieval: dict[str, Any], exc: Exception) -> str:
    first = (retrieval.get("results") or [{}])[0]
    chunk_id = first.get("chunk_id", "source inconnue")
    page_start = first.get("page_start", "?")
    page_end = first.get("page_end", "?")
    attribution = retrieval.get("agent_attribution") or "According to the Khadamati legal expert agent"
    excerpt = str(first.get("excerpt") or "").strip()
    short_excerpt = excerpt[:420] + ("..." if len(excerpt) > 420 else "")
    return (
        f"{attribution}. L-model ma jawbch daba, walakin l-knowledge graph l9a source m9arba. "
        f"Source: {chunk_id}, pages {page_start}-{page_end}. "
        f" مقتطف: {short_excerpt} "
        "Hadi ma3louma qanouniya 3amma, machi istichara niha2iya."
    )


def _local_rag_answer(retrieval: dict[str, Any]) -> str:
    first = (retrieval.get("results") or [{}])[0]
    route = retrieval.get("route") or {}
    attribution = retrieval.get("agent_attribution") or "According to the Khadamati legal expert agent"
    merge_strategy = retrieval.get("merge_strategy")

    def source_sentence(item: dict[str, Any], limit: int = 320) -> str:
        chunk_id = item.get("chunk_id", "source inconnue")
        page_start = item.get("page_start", "?")
        page_end = item.get("page_end", "?")
        primary_article = item.get("primary_article")
        article_count = int(item.get("article_count") or 0)
        agent_label = item.get("agent_label") or item.get("legal_sector") or "legal expert agent"
        if primary_article and article_count > 1:
            article_note = f"kaynin {article_count} articles/fosoul; l-aqrab howa {primary_article}"
        elif primary_article:
            article_note = f"l-aqrab source howa {primary_article}"
        else:
            article_note = "article ma banhach b wodo7"
        excerpt = str(item.get("excerpt") or "").strip()
        compact = " ".join(excerpt.split())[:limit]
        return f"{agent_label}: {article_note}. Source {chunk_id}, pages {page_start}-{page_end}. {compact}"

    if merge_strategy == "multi_agent_graph_merge":
        seen_agents: set[str] = set()
        merged_parts: list[str] = []
        for item in retrieval.get("results", []):
            agent_id = str(item.get("agent_id") or item.get("sector") or "")
            if agent_id in seen_agents:
                continue
            seen_agents.add(agent_id)
            merged_parts.append(source_sentence(item, limit=260))
            if len(merged_parts) >= 3:
                break
        return (
            f"{attribution}. Khadamati dmj had l-agents f knowledge graph. "
            + " ".join(merged_parts)
            + " Hadi ma3louma qanouniya 3amma, machi istichara niha2iya."
        )

    return (
        f"{attribution}. "
        f"Route: {route.get('legal_sector', 'Legal KG')}. "
        f"{source_sentence(first, limit=520)} "
        "Hadi ma3louma qanouniya 3amma, machi istichara niha2iya."
    )


async def _stream_chat_completion(answer: str, model: str):
    completion_id = f"chatcmpl-khadamati-{int(time.time() * 1000)}"
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
            "Le service Khadamati n'est pas configure pour le moment."
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
