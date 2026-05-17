from __future__ import annotations

import json
import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DEFAULT_RAG_DIR = PROJECT_DIR / "rag_datasets"

ARABIC_RE = re.compile(r"[\u0600-\u06ff]+")
TOKEN_RE = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)
ARTICLE_RE = re.compile(
    r"(?:المادة|الفصل)\s*([0-9٠-٩]+(?:\s*[-‐‑–—]\s*[0-9٠-٩]+)?)",
    re.UNICODE,
)

SECTOR_HINTS: dict[str, tuple[str, ...]] = {
    "family_law": (
        "family",
        "divorce",
        "marriage",
        "custody",
        "hadana",
        "l7adana",
        "nafaka",
        "talaq",
        "zawaj",
        "7adana",
        "الأسرة",
        "زواج",
        "طلاق",
        "نفقة",
        "حضانة",
        "نسب",
        "إرث",
    ),
    "criminal_law": (
        "criminal",
        "crime",
        "theft",
        "sari9a",
        "sariqa",
        "steal",
        "assault",
        "prison",
        "penalty",
        "جنائي",
        "جريمة",
        "سرقة",
        "عقوبة",
        "حبس",
        "سجن",
        "ضرب",
    ),
    "civil_procedure": (
        "civil",
        "procedure",
        "appeal",
        "judgment",
        "execution",
        "court",
        "lawsuit",
        "استئناف",
        "استيناف",
        "االستيناف",
        "حكم",
        "تنفيذ",
        "دعوى",
        "محكمة",
        "المسطرة",
        "المدنية",
    ),
    "constitutional_law": (
        "constitution",
        "rights",
        "parliament",
        "government",
        "king",
        "freedom",
        "دستور",
        "حقوق",
        "حريات",
        "الملك",
        "البرلمان",
        "الحكومة",
    ),
    "public_finance": (
        "tax",
        "finance",
        "budget",
        "customs",
        "vat",
        "tva",
        "ضريبة",
        "مالية",
        "ميزانية",
        "جمارك",
        "الرسم",
    ),
}

QUERY_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "talaq": ("طلاق", "التطليق", "الزوجين"),
    "divorce": ("طلاق", "التطليق", "الزوجين"),
    "zawaj": ("زواج", "الزواج", "الزوجين"),
    "nafaka": ("نفقة", "النفقة"),
    "custody": ("حضانة", "الحضانة", "حضانتهم", "حضان"),
    "7adana": ("حضانة", "الحضانة", "حضانتهم", "حضان"),
    "hadana": ("حضانة", "الحضانة", "حضانتهم", "حضان"),
    "l7adana": ("حضانة", "الحضانة", "حضانتهم", "حضان"),
    "الحدانة": ("حضانة", "الحضانة", "حضانتهم", "حضان"),
    "steal": ("سرقة", "العقوبة"),
    "theft": ("سرقة", "العقوبة"),
    "sari9a": ("سرقة", "السرقة", "العقوبة"),
    "sariqa": ("سرقة", "السرقة", "العقوبة"),
    "prison": ("حبس", "سجن", "العقوبة"),
    "court": ("محكمة", "الحكم", "الدعوى"),
    "appeal": ("استئناف", "الاستئناف", "استيناف", "االستيناف", "الطعن", "طعن"),
    "استئناف": ("الاستئناف", "استيناف", "االستيناف", "الطعن", "طعن"),
    "الاستئناف": ("استئناف", "استيناف", "االستيناف", "الطعن", "طعن"),
    "tax": ("ضريبة", "الرسم", "الجبايات"),
}


@dataclass(frozen=True)
class LoadedSector:
    slug: str
    metadata: dict[str, Any]
    agent: dict[str, Any]
    chunks: tuple[dict[str, Any], ...]
    token_counters: tuple[Counter[str], ...]


def rag_root() -> Path:
    configured = os.getenv("LEGAL_RAG_DIR")
    return Path(configured) if configured else DEFAULT_RAG_DIR


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _tokens(text: str) -> list[str]:
    raw = [token.lower() for token in TOKEN_RE.findall(text or "")]
    expanded: list[str] = []
    for token in raw:
        expanded.append(token)
        expanded.extend(QUERY_EXPANSIONS.get(token, ()))
    return expanded


@lru_cache(maxsize=1)
def load_legal_rag() -> dict[str, Any]:
    root = rag_root()
    manifest = _read_json(root / "manifest.json")
    registry = _read_json(root / "agent_registry.json")
    agents_by_sector = {agent["sector"]: agent for agent in registry.get("agents", [])}
    sectors: dict[str, LoadedSector] = {}

    for sector_meta in manifest.get("sectors", []):
        slug = sector_meta["slug"]
        sector_dir = root / "sectors" / slug
        chunks = tuple(_read_jsonl(sector_dir / "chunks.jsonl"))
        counters = tuple(Counter(_tokens(chunk.get("text", ""))) for chunk in chunks)
        sectors[slug] = LoadedSector(
            slug=slug,
            metadata=_read_json(sector_dir / "metadata.json"),
            agent=agents_by_sector.get(slug, {}),
            chunks=chunks,
            token_counters=counters,
        )

    return {
        "root": str(root),
        "manifest": manifest,
        "registry": registry,
        "sectors": sectors,
    }


def legal_rag_status() -> dict[str, Any]:
    started = time.perf_counter()
    data = load_legal_rag()
    sectors: dict[str, LoadedSector] = data["sectors"]
    return {
        "ready": True,
        "root": data["root"],
        "version": data["manifest"].get("version"),
        "built_at": data["manifest"].get("built_at"),
        "sector_count": len(sectors),
        "chunk_count": sum(len(sector.chunks) for sector in sectors.values()),
        "sectors": [
            {
                "slug": sector.slug,
                "legal_sector": sector.metadata.get("legal_sector"),
                "legal_sector_ar": sector.metadata.get("legal_sector_ar"),
                "source_file": sector.metadata.get("source_file"),
                "page_count": sector.metadata.get("page_count"),
                "chunk_count": sector.metadata.get("chunk_count"),
                "agent_id": sector.agent.get("agent_id"),
            }
            for sector in sectors.values()
        ],
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def route_legal_sector(question: str, preferred_sector: str | None = None) -> dict[str, Any]:
    data = load_legal_rag()
    sectors: dict[str, LoadedSector] = data["sectors"]
    if preferred_sector and preferred_sector in sectors:
        sector = sectors[preferred_sector]
        return _sector_route_payload(sector, 1.0, "explicit")

    token_set = set(_tokens(question))
    lowered = question.lower()
    scored: list[tuple[float, LoadedSector]] = []
    for slug, sector in sectors.items():
        hints = SECTOR_HINTS.get(slug, ())
        score = 0.0
        for hint in hints:
            hint_l = hint.lower()
            if hint_l in token_set:
                score += 3
            elif hint_l in lowered:
                score += 2
        scored.append((score, sector))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best_sector = scored[0]
    if best_score <= 0:
        best_sector = sectors.get("civil_procedure") or next(iter(sectors.values()))
        best_score = 1.0
    confidence = min(0.95, 0.45 + best_score * 0.07)
    return _sector_route_payload(best_sector, confidence, "keyword")


def _sector_route_payload(sector: LoadedSector, confidence: float, route_type: str) -> dict[str, Any]:
    return {
        "sector": sector.slug,
        "legal_sector": sector.metadata.get("legal_sector"),
        "legal_sector_ar": sector.metadata.get("legal_sector_ar"),
        "agent_id": sector.agent.get("agent_id"),
        "scope": sector.agent.get("scope"),
        "confidence": round(confidence, 2),
        "route_type": route_type,
    }


def retrieve_legal_context(
    *,
    question: str,
    sector: str | None = None,
    top_k: int = 4,
) -> dict[str, Any]:
    started = time.perf_counter()
    data = load_legal_rag()
    sectors: dict[str, LoadedSector] = data["sectors"]
    route = route_legal_sector(question, sector)
    selected = sectors[route["sector"]]

    query_counter = Counter(_tokens(question))
    ranked: list[tuple[float, dict[str, Any]]] = []
    for chunk, counter in zip(selected.chunks, selected.token_counters, strict=True):
        score = _score_chunk(query_counter, counter, chunk)
        if score > 0:
            ranked.append((score, chunk))

    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked:
        ranked = [(0.01, chunk) for chunk in selected.chunks[:top_k]]

    results = [
        _chunk_result(score, chunk, query_counter)
        for score, chunk in ranked[: max(1, min(top_k, 8))]
    ]
    retrieval_ms = (time.perf_counter() - started) * 1000

    return {
        "question": question,
        "route": route,
        "results": results,
        "a2a_trace": [
            {
                "agent": "khadamati_legal_master",
                "role": "master_router",
                "action": "selected_sector",
                "target": route["agent_id"],
            },
            {
                "agent": route["agent_id"],
                "role": "sector_expert",
                "action": "retrieved_rag_context",
                "target": "legal_rag_retriever",
            },
        ],
        "retrieval_ms": round(retrieval_ms, 2),
    }


def _score_chunk(query: Counter[str], chunk_tokens: Counter[str], chunk: dict[str, Any]) -> float:
    score = 0.0
    chunk_len = max(sum(chunk_tokens.values()), 1)
    text_lower = str(chunk.get("text") or "").lower()
    for token, q_count in query.items():
        count = chunk_tokens.get(token, 0)
        if count:
            score += (1 + math.log(count)) * (1 + math.log(q_count))
        elif len(token) >= 4 and token in text_lower:
            score += 0.75 * (1 + math.log(q_count))
    for article_ref in chunk.get("article_refs", []):
        if any(token in str(article_ref).lower() for token in query):
            score += 2.5
    if "الفهرس" in text_lower or "................................" in text_lower:
        score *= 0.25
    quality = float(chunk.get("metrics", {}).get("quality_score") or 0.5)
    return (score / math.sqrt(chunk_len)) * (0.75 + quality)


def _extract_articles(text: str) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in ARTICLE_RE.finditer(text):
        number = " ".join(match.group(1).replace("‐", "-").replace("‑", "-").split())
        label = f"{match.group(0).split()[0]} {number}"
        if label in seen:
            continue
        seen.add(label)
        articles.append({"label": label, "offset": match.start()})
    return articles


def _query_anchor(text: str, query: Counter[str]) -> int | None:
    lowered = text.lower()
    best: int | None = None
    for token in query:
        if len(token) < 4:
            continue
        position = lowered.find(token.lower())
        if position >= 0 and (best is None or position < best):
            best = position
    return best


def _nearest_article(text: str, query: Counter[str]) -> tuple[str | None, list[str]]:
    articles = _extract_articles(text)
    if not articles:
        return None, []
    anchor = _query_anchor(text, query)
    if anchor is None:
        primary = articles[0]
    else:
        primary = min(articles, key=lambda item: abs(int(item["offset"]) - anchor))
    return str(primary["label"]), [str(item["label"]) for item in articles]


def _chunk_result(score: float, chunk: dict[str, Any], query: Counter[str]) -> dict[str, Any]:
    text = str(chunk.get("text") or "").strip()
    excerpt = text[:900] + ("..." if len(text) > 900 else "")
    primary_article, extracted_articles = _nearest_article(text, query)
    article_refs = list(dict.fromkeys([*(chunk.get("article_refs") or []), *extracted_articles]))
    if not primary_article and article_refs:
        primary_article = str(article_refs[0])
    return {
        "score": round(float(score), 4),
        "chunk_id": chunk.get("chunk_id"),
        "sector": chunk.get("sector"),
        "legal_sector": chunk.get("legal_sector"),
        "source_file": chunk.get("source_file"),
        "source_title": chunk.get("source_title"),
        "source_title_ar": chunk.get("source_title_ar"),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "article_refs": article_refs,
        "primary_article": primary_article,
        "article_count": len(article_refs),
        "article_notice": "many_articles_nearby" if len(article_refs) > 1 else "",
        "headings": chunk.get("headings") or [],
        "excerpt": excerpt,
    }


def build_legal_answer_prompt(question: str, retrieval: dict[str, Any]) -> tuple[str, str]:
    context_blocks = []
    for index, item in enumerate(retrieval.get("results", []), start=1):
        context_blocks.append(
            "\n".join(
                [
                    f"Source {index}: {item['chunk_id']}",
                    f"Sector: {item['legal_sector']}",
                    f"Pages: {item['page_start']}-{item['page_end']}",
                    f"Nearest article: {item.get('primary_article') or 'not detected'}",
                    f"Articles: {', '.join(item['article_refs']) if item['article_refs'] else 'not detected'}",
                    f"Text: {item['excerpt']}",
                ]
            )
        )

    system_instruction = """
You are Khadamati, a Moroccan first-line legal and bureaucracy hotline assistant.
Use only the provided retrieved legal context for legal claims.
Answer in concise Moroccan Darija if the user uses Darija, otherwise use simple French.
Start with the nearest detected article/fasl/madda when present.
If several articles are present, say that there are several and name the nearest one first.
Always include a short safety note that this is legal information, not a final lawyer opinion.
Mention article, source chunk IDs, and pages compactly.
If context is weak or outside scope, say that clearly and ask one next question.
""".strip()
    prompt = f"Question:\n{question}\n\nRetrieved context:\n\n" + "\n\n".join(context_blocks)
    return system_instruction, prompt
