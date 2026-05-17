from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DEFAULT_CONFIG_FILE = PROJECT_DIR / "config" / "hotline" / "experts.json"
DEFAULT_LOG_DIR = PROJECT_DIR / "logs"
DEFAULT_SUBMISSIONS_FILE = DEFAULT_LOG_DIR / "mock_chikaya_submissions.jsonl"
DEFAULT_APPROVAL_FILE = DEFAULT_LOG_DIR / "oral_approvals.jsonl"

LEGAL_SAFETY_TERMS = {
    "arrest",
    "court",
    "deadline",
    "detention",
    "eviction",
    "minor",
    "police",
    "summons",
    "threat",
    "violence",
}


@dataclass(frozen=True)
class Expert:
    id: str
    label: str
    model_hint: str
    dataset_path: str
    mission: str
    routing_keywords: tuple[str, ...]
    required_fields: tuple[str, ...]
    evidence_checklist: tuple[str, ...]
    next_questions: tuple[str, ...]
    escalation_rules: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Expert":
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            model_hint=str(data.get("model_hint") or "gemini-live-expert"),
            dataset_path=str(data.get("dataset_path") or ""),
            mission=str(data.get("mission") or ""),
            routing_keywords=tuple(str(item).lower() for item in data.get("routing_keywords", [])),
            required_fields=tuple(str(item) for item in data.get("required_fields", [])),
            evidence_checklist=tuple(str(item) for item in data.get("evidence_checklist", [])),
            next_questions=tuple(str(item) for item in data.get("next_questions", [])),
            escalation_rules=tuple(str(item).lower() for item in data.get("escalation_rules", [])),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "model_hint": self.model_hint,
            "dataset_path": self.dataset_path,
            "mission": self.mission,
            "required_fields": list(self.required_fields),
            "evidence_checklist": list(self.evidence_checklist),
            "next_questions": list(self.next_questions),
            "escalation_rules": list(self.escalation_rules),
        }


def _config_file() -> Path:
    configured = os.getenv("HOTLINE_EXPERTS_FILE")
    return Path(configured) if configured else DEFAULT_CONFIG_FILE


def _submission_file() -> Path:
    configured = os.getenv("MOCK_CHIKAYA_LOG_FILE")
    return Path(configured) if configured else DEFAULT_SUBMISSIONS_FILE


def _approval_file() -> Path:
    configured = os.getenv("ORAL_APPROVAL_LOG_FILE")
    return Path(configured) if configured else DEFAULT_APPROVAL_FILE


def _load_config() -> dict[str, Any]:
    path = _config_file()
    return json.loads(path.read_text(encoding="utf-8"))


def load_experts() -> list[Expert]:
    config = _load_config()
    return [Expert.from_mapping(item) for item in config.get("experts", [])]


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9_+]+", text.lower()) if token}


def _keyword_score(text: str, tokens: set[str], expert: Expert) -> int:
    score = 0
    lowered = text.lower()
    for keyword in expert.routing_keywords:
        if " " in keyword:
            if keyword in lowered:
                score += 3
        elif keyword in tokens:
            score += 2
        elif keyword and keyword in lowered:
            score += 1
    return score


def _risk_flags(text: str) -> list[str]:
    tokens = _tokenize(text)
    lowered = text.lower()
    flags = sorted(term for term in LEGAL_SAFETY_TERMS if term in tokens or term in lowered)
    if any(word in lowered for word in ("today", "tomorrow", "24h", "urgent", "daba")):
        flags.append("time_sensitive")
    return flags


def _missing_fields(expert: Expert, provided: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in expert.required_fields:
        value = provided.get(field)
        if value is None or str(value).strip() == "":
            missing.append(field)
    return missing


def route_issue(
    *,
    message: str,
    language: str = "darija",
    provided_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    experts = load_experts()
    provided = provided_fields or {}
    tokens = _tokenize(message)
    scored = [
        {
            "expert": expert,
            "score": _keyword_score(message, tokens, expert),
        }
        for expert in experts
    ]
    scored.sort(key=lambda item: item["score"], reverse=True)

    selected = scored[0]["expert"] if scored and scored[0]["score"] > 0 else _default_expert(experts)
    flags = _risk_flags(message)
    if flags and selected.id != "legal_safety":
        legal = next((expert for expert in experts if expert.id == "legal_safety"), None)
        if legal and any(flag in LEGAL_SAFETY_TERMS for flag in flags):
            selected = legal

    selected_score = next((item["score"] for item in scored if item["expert"].id == selected.id), 0)
    confidence = min(0.95, 0.35 + (selected_score * 0.08))
    missing = _missing_fields(selected, provided)

    return {
        "language": language,
        "selected_expert": selected.public_dict(),
        "confidence": round(confidence, 2),
        "candidate_experts": [
            {
                "id": item["expert"].id,
                "label": item["expert"].label,
                "score": item["score"],
                "model_hint": item["expert"].model_hint,
            }
            for item in scored[:3]
        ],
        "missing_fields": missing,
        "risk_flags": flags,
        "next_questions": list(selected.next_questions[:3]),
        "evidence_checklist": list(selected.evidence_checklist),
        "recommended_action": _recommended_action(selected, missing, flags),
        "safety_notice": _safety_notice(flags),
        "dataset_status": {
            "path": selected.dataset_path,
            "ready": _dataset_has_non_placeholder_records(selected.dataset_path),
        },
    }


def _default_expert(experts: list[Expert]) -> Expert:
    return next((expert for expert in experts if expert.id == "admin_triage"), experts[0])


def _recommended_action(expert: Expert, missing: list[str], flags: list[str]) -> str:
    if flags:
        return "Collect urgent facts and escalate to a qualified human reviewer before giving procedural guidance."
    if missing:
        return "Ask the missing intake questions, then draft a structured action plan."
    if expert.id == "chikaya_complaints":
        return "Prepare a complaint packet and request explicit consent before mock submission."
    return "Give short practical next steps and offer complaint drafting if the caller wants it."


def _safety_notice(flags: list[str]) -> str:
    if flags:
        return (
            "This can involve legal or safety risk. Do not present a final legal opinion; "
            "collect facts and recommend qualified human help for urgent or high-risk cases."
        )
    return (
        "Provide administrative information and document-preparation help, not a binding legal opinion."
    )


def _dataset_has_non_placeholder_records(dataset_path: str) -> bool:
    if not dataset_path:
        return False
    path = PROJECT_DIR / dataset_path
    if not path.exists():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and "placeholder" not in line.lower():
                return True
    except OSError:
        return False
    return False


def hotline_system_prompt(base_prompt: str) -> str:
    experts = load_experts()
    expert_lines = "\n".join(
        f"- {expert.label}: {expert.mission} Dataset: {expert.dataset_path}. Model hint: {expert.model_hint}."
        for expert in experts
    )
    return f"""{base_prompt}

BUREAUCRACY AND LEGAL HOTLINE MODE:
You are a first-line Moroccan public-services hotline, not a lawyer and not a court.
Route each caller to one expert desk before answering. Use route_hotline_issue when the caller asks about bureaucracy, complaints, work, consumer issues, courts, police, documents, or public services.
Keep phone answers short. Ask only the next missing question. Do not invent law, deadlines, offices, or document requirements.
For high-risk legal, safety, police, court, eviction, violence, or minor-related matters, recommend a qualified human professional or emergency help.
Never submit anything unless the caller clearly consents. For this prototype, complaint submission is mock-only.

AVAILABLE EXPERT DESKS:
{expert_lines}
""".strip()


def build_complaint_packet(payload: dict[str, Any]) -> dict[str, Any]:
    subject = str(payload.get("subject") or "").strip()
    description = str(payload.get("description") or "").strip()
    desired_resolution = str(payload.get("desired_resolution") or "").strip()
    city = str(payload.get("city") or "").strip()
    category = str(payload.get("category") or "administrative").strip()

    summary_parts = [
        f"Category: {category}",
        f"City: {city}",
        f"Subject: {subject}",
        f"Problem: {description}",
        f"Requested resolution: {desired_resolution}",
    ]
    return {
        "category": category,
        "subject": subject,
        "summary": "\n".join(part for part in summary_parts if not part.endswith(": ")),
        "evidence": payload.get("evidence") or [],
        "human_review_required": bool(_risk_flags(description + " " + subject)),
    }


async def submit_mock_chikaya(payload: dict[str, Any]) -> dict[str, Any]:
    required = [
        "citizen_name",
        "phone",
        "city",
        "category",
        "subject",
        "description",
        "desired_resolution",
    ]
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        return {
            "submitted": False,
            "mode": "mock",
            "missing_fields": missing,
            "steps": ["Mock portal not opened because required fields are missing."],
        }
    if payload.get("consent") is not True:
        return {
            "submitted": False,
            "mode": "mock",
            "missing_fields": ["consent"],
            "steps": ["Mock portal not opened because explicit consent is required."],
        }

    packet = build_complaint_packet(payload)
    receipt_id = _receipt_id(payload)
    event = {
        "receipt_id": receipt_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "mock",
        "citizen_name": payload.get("citizen_name"),
        "phone": payload.get("phone"),
        "city": payload.get("city"),
        "category": packet["category"],
        "subject": packet["subject"],
        "summary": packet["summary"],
        "evidence": packet["evidence"],
        "human_review_required": packet["human_review_required"],
    }

    await asyncio.to_thread(_append_submission, event)
    return {
        "submitted": True,
        "mode": "mock",
        "receipt_id": receipt_id,
        "packet": packet,
        "steps": [
            "Opened mock Chikaya portal.",
            "Selected complaint category.",
            "Filled citizen identity and contact fields.",
            "Inserted structured complaint summary.",
            "Submitted mock complaint and stored audit receipt.",
        ],
    }


async def start_oral_approval(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "mock_chikaya_submit").strip()
    summary = str(payload.get("summary") or "").strip()
    approval_id = _approval_id(action, summary)
    event = {
        "approval_id": approval_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "summary": summary,
        "status": "pending",
        "required_phrase": "mwafeq",
    }
    await asyncio.to_thread(_append_approval, event)
    return {
        "approval_id": approval_id,
        "status": "pending",
        "required_phrase": "mwafeq",
        "oral_prompt": (
            "Bach nkemmel had l-action f demo, khass l-user ygol b-wodo7: mwafeq. "
            "Ila ma galhach, matdir ta submit."
        ),
        "action": action,
        "summary": summary,
    }


async def confirm_oral_approval(payload: dict[str, Any]) -> dict[str, Any]:
    approval_id = str(payload.get("approval_id") or "").strip()
    spoken_text = str(payload.get("spoken_text") or "").lower()
    approved = any(phrase in spoken_text for phrase in ("mwafeq", "موافق", "oui", "j'accepte", "agree", "yes"))
    event = {
        "approval_id": approval_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "approved" if approved else "rejected",
        "spoken_text": spoken_text[:300],
    }
    await asyncio.to_thread(_append_approval, event)
    return {
        "approval_id": approval_id,
        "approved": approved,
        "status": "approved" if approved else "rejected",
        "message": "Oral approval confirmed." if approved else "Approval phrase not detected.",
    }


def _receipt_id(payload: dict[str, Any]) -> str:
    seed = json.dumps(payload, sort_keys=True, ensure_ascii=True) + datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8].upper()
    return f"MOCK-CHIKAYA-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{digest}"


def _approval_id(action: str, summary: str) -> str:
    seed = f"{action}:{summary}:{datetime.now(timezone.utc).isoformat()}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:10].upper()
    return f"APPROVAL-{digest}"


def _append_submission(event: dict[str, Any]) -> None:
    path = _submission_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _append_approval(event: dict[str, Any]) -> None:
    path = _approval_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


async def read_mock_submissions(limit: int = 50) -> list[dict[str, Any]]:
    path = _submission_file()
    if not path.exists():
        return []
    return await asyncio.to_thread(_read_submissions_sync, path, limit)


def _read_submissions_sync(path: Path, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(records))
