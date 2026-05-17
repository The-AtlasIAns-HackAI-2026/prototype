from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LOG_DIR = BASE_DIR / "logs" if (BASE_DIR / "logs").exists() else BASE_DIR.parent / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "events.jsonl"
_lock = asyncio.Lock()

SAFE_METADATA_KEYS = {
    "agent_id",
    "approval_id",
    "article",
    "call_id",
    "call_status",
    "caller_phone",
    "channel",
    "conversation_id",
    "direction",
    "latency_ms",
    "participant_identity",
    "provider",
    "receipt_id",
    "route",
    "room_name",
    "sector",
    "source",
    "tool",
    "trace_id",
    "workflow",
}


def _log_path() -> Path:
    configured = os.getenv("LOG_FILE")
    return Path(configured) if configured else DEFAULT_LOG_FILE


def _safe_word_count(text: str | None) -> int:
    if not text:
        return 0
    return len([part for part in text.split() if part.strip()])


def _mask_phone(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    digits = [char for char in raw if char.isdigit()]
    if len(digits) <= 4:
        return "***"
    return f"***{''.join(digits[-4:])}"


def _safe_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in SAFE_METADATA_KEYS or value in (None, ""):
            continue
        if key == "caller_phone":
            safe[key] = _mask_phone(value)
        elif isinstance(value, (str, int, float, bool)):
            safe[key] = str(value)[:180] if isinstance(value, str) else value
    return safe


async def log_event(
    *,
    topic: str,
    language: str,
    success: bool,
    response_text: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "topic": topic[:80],
        "language": language,
        "success": bool(success),
        "word_count": _safe_word_count(response_text),
    }

    if metadata:
        safe_metadata = _safe_metadata(metadata)
        if safe_metadata:
            event["metadata"] = safe_metadata

    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    async with _lock:
        await asyncio.to_thread(_append_json_line, path, event)

    return event


def _append_json_line(path: Path, event: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


async def read_events(limit: int = 200) -> list[dict[str, Any]]:
    path = _log_path()
    if not path.exists():
        return []

    return await asyncio.to_thread(_read_events_sync, path, limit)


def _read_events_sync(path: Path, limit: int) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


async def analytics_summary(limit: int = 500) -> dict[str, Any]:
    events = await read_events(limit)
    language_counts = Counter(event.get("language", "unknown") for event in events)
    topic_counts = Counter(event.get("topic", "unknown") for event in events)
    channel_counts = Counter(
        (event.get("metadata") or {}).get("channel", "unknown") for event in events
    )
    tool_counts = Counter(
        (event.get("metadata") or {}).get("tool", "none") for event in events
    )
    successful = sum(1 for event in events if event.get("success") is True)
    total_words = sum(int(event.get("word_count") or 0) for event in events)

    return {
        "total_events": len(events),
        "successful_events": successful,
        "success_rate": round(successful / len(events), 3) if events else 0,
        "total_words": total_words,
        "average_words": round(total_words / len(events), 1) if events else 0,
        "languages": dict(language_counts),
        "channels": dict(channel_counts),
        "tools": dict(tool_counts),
        "top_topics": topic_counts.most_common(8),
        "recent": list(reversed(events[-20:])),
    }
