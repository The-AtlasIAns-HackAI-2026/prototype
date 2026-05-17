#!/usr/bin/env python3
"""Build sector-separated RAG datasets from the local Moroccan legal PDFs.

Outputs are intentionally simple and portable:
- pages.jsonl: page-level extracted text and quality metrics
- chunks.jsonl: retrieval chunks with legal/source metadata
- embeddings.npy: dense normalized embeddings, one row per chunk
- metadata.json: source/build metadata for the sector
- manifest.json and agent_registry.json at the dataset root
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import fitz
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "rag_datasets"

BIDI_CONTROLS = dict.fromkeys(
    map(
        ord,
        "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069",
    ),
    None,
)

ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufeff]")
ARABIC_DIACRITIC_RE = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
ORDINAL_WORDS = (
    "الأول|الأولى|الثاني|الثانية|الثالث|الثالثة|الرابع|الرابعة|الخامس|الخامسة|"
    "السادس|السادسة|السابع|السابعة|الثامن|الثامنة|التاسع|التاسعة|العاشر|العاشرة|"
    "الحادي عشر|الحادية عشرة|الثاني عشر|الثانية عشرة"
)
ARTICLE_RE = re.compile(
    rf"(?:المادة|الفصل)\s+(?:(?:[0-9٠-٩]+(?:\s*[-./]\s*[0-9٠-٩]+)*)(?:\s+مكرر)?|(?:{ORDINAL_WORDS}))",
    re.UNICODE,
)
HEADING_RE = re.compile(
    r"^(?:الباب|القسم|الفرع|الكتاب|الجزء|تصدير|ديباجة|الفصل|المادة)\b.{0,100}$",
    re.UNICODE,
)


@dataclass(frozen=True)
class SectorSpec:
    slug: str
    legal_sector: str
    legal_sector_ar: str
    source_pdf: str
    title: str
    title_ar: str
    extraction_mode: str
    agent_id: str
    agent_scope: str


SECTORS: tuple[SectorSpec, ...] = (
    SectorSpec(
        slug="family_law",
        legal_sector="Family law",
        legal_sector_ar="قانون الأسرة",
        source_pdf="family-law-morocco.pdf",
        title="Moroccan Family Code",
        title_ar="مدونة الأسرة",
        extraction_mode="native",
        agent_id="morocco_family_law_agent",
        agent_scope="Marriage, divorce, filiation, custody, inheritance-related family code provisions, and family court procedure in the Moroccan Family Code.",
    ),
    SectorSpec(
        slug="constitutional_law",
        legal_sector="Constitutional law",
        legal_sector_ar="القانون الدستوري",
        source_pdf="constitution.pdf",
        title="Constitution of the Kingdom of Morocco 2011",
        title_ar="دستور المملكة المغربية 2011",
        extraction_mode="native",
        agent_id="morocco_constitutional_law_agent",
        agent_scope="Constitutional institutions, rights and freedoms, separation of powers, territorial organization, constitutional review, and transitional provisions.",
    ),
    SectorSpec(
        slug="civil_procedure",
        legal_sector="Civil procedure",
        legal_sector_ar="المسطرة المدنية",
        source_pdf="civil.pdf",
        title="Moroccan Code of Civil Procedure",
        title_ar="قانون المسطرة المدنية",
        extraction_mode="native",
        agent_id="morocco_civil_procedure_agent",
        agent_scope="Civil litigation procedure, jurisdiction, judgments, appeals, enforcement, and related procedural rules.",
    ),
    SectorSpec(
        slug="criminal_law",
        legal_sector="Criminal law",
        legal_sector_ar="القانون الجنائي",
        source_pdf="criminal-laws.pdf",
        title="Moroccan Criminal Code",
        title_ar="مجموعة القانون الجنائي",
        extraction_mode="ocr",
        agent_id="morocco_criminal_law_agent",
        agent_scope="Crimes, penalties, aggravating and mitigating circumstances, offences against persons, property, public order, and criminal-code classifications.",
    ),
    SectorSpec(
        slug="public_finance",
        legal_sector="Public finance and tax law",
        legal_sector_ar="المالية العمومية والجبايات",
        source_pdf="finance-project-2026.pdf",
        title="Finance Bill No. 50.25 for Fiscal Year 2026",
        title_ar="مشروع قانون المالية رقم 50.25 للسنة المالية 2026",
        extraction_mode="native",
        agent_id="morocco_public_finance_agent",
        agent_scope="Public resources, tax and customs provisions, borrowing authorization, budget balance, public charges, and finance-bill measures for fiscal year 2026.",
    ),
)


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            count += 1
    return count


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(BIDI_CONTROLS)
    text = text.replace("\x00", " ")
    text = text.replace("\ufeff", " ")
    text = re.sub(r"[ \t\xa0]+", " ", text)
    lines: list[str] = []
    previous_blank = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if is_noise_line(line):
            continue
        if not line:
            if not previous_blank:
                lines.append("")
            previous_blank = True
            continue
        previous_blank = False
        if re.fullmatch(r"[-–—]?\s*\d+\s*[-–—]?", line):
            continue
        if re.fullmatch(r"[.·•ـ\s]{5,}", line):
            continue
        lines.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def is_noise_line(line: str) -> bool:
    if not line:
        return False
    arabic = len(ARABIC_RE.findall(line))
    letters = sum(ch.isalpha() for ch in line)
    if arabic == 0 and len(line) < 40 and letters < 8:
        return True
    if re.fullmatch(r"[-–—]?\s*\d+\s*[-–—]?", line):
        return True
    if re.fullmatch(r"[.·•ـ\s]{5,}", line):
        return True
    compact = ARABIC_DIACRITIC_RE.sub("", line)
    compact = re.sub(r"\s+", "", compact)
    short = len(line) < 140
    if short and "التشريع" in compact and (
        "المملكة" in compact
        or "المغربية" in compact
        or "وزارة" in compact
        or "العدل" in compact
        or "العذل" in compact
        or "مديرية" in compact
        or "مذيرية" in compact
        or "مكيرية" in compact
    ):
        return True
    if short and "مركزالدراسات" in compact and "السياسةالجنائية" in compact:
        return True
    return False


def text_metrics(text: str) -> dict:
    chars = len(text)
    arabic = len(ARABIC_RE.findall(text))
    diacritics = len(ARABIC_DIACRITIC_RE.findall(text))
    controls = sum(
        1
        for ch in text
        if unicodedata.category(ch)[0] == "C" and ch not in {"\n", "\t", "\r"}
    )
    replacement = text.count("\ufffd")
    latin_noise = len(re.findall(r"[ŒœŠšŽžŸ]", text))
    arabic_ratio = arabic / max(chars, 1)
    diacritic_ratio = diacritics / max(arabic, 1)
    noise_ratio = (controls + replacement + latin_noise) / max(chars, 1)
    length_score = min(chars / 900, 1.0)
    quality = (
        (0.30 * length_score)
        + (0.45 * min(arabic_ratio / 0.55, 1.0))
        + (0.15 * max(0.0, 1.0 - min(diacritic_ratio / 0.12, 1.0)))
        + (0.10 * max(0.0, 1.0 - min(noise_ratio / 0.03, 1.0)))
    )
    return {
        "chars": chars,
        "arabic_chars": arabic,
        "arabic_ratio": round(arabic_ratio, 4),
        "diacritic_ratio": round(diacritic_ratio, 4),
        "noise_ratio": round(noise_ratio, 4),
        "quality_score": round(quality, 4),
    }


def tesseract_available() -> bool:
    try:
        result = subprocess.run(
            ["tesseract", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def ocr_page(page: fitz.Page, dpi: int) -> str:
    scale = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    env = os.environ.copy()
    env.setdefault("OMP_THREAD_LIMIT", "1")
    with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
        pix.save(image_file.name)
        result = subprocess.run(
            [
                "tesseract",
                image_file.name,
                "stdout",
                "-l",
                "ara+eng",
                "--psm",
                "6",
                "--dpi",
                str(dpi),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
    if result.returncode != 0:
        return ""
    return normalize_text(result.stdout)


def native_page_text(page: fitz.Page) -> str:
    text = page.get_text("text", sort=True)
    if not text.strip():
        blocks = page.get_text("blocks", sort=True)
        text = "\n".join(str(block[4]) for block in blocks if len(block) > 4)
    return normalize_text(text)


def extract_pages(pdf_path: Path, spec: SectorSpec, dpi: int, ocr_low_quality: bool) -> tuple[list[dict], dict]:
    doc = fitz.open(pdf_path)
    use_ocr = spec.extraction_mode == "ocr"
    if use_ocr and not tesseract_available():
        raise RuntimeError("criminal_law requires OCR, but tesseract is not available")

    pages: list[dict] = []
    extraction_counts: dict[str, int] = {}
    for page_index in range(len(doc)):
        page = doc[page_index]
        native = native_page_text(page)
        native_metrics = text_metrics(native)
        selected_text = native
        selected_source = "native"
        selected_metrics = native_metrics

        if use_ocr or (
            ocr_low_quality
            and native_metrics["quality_score"] < 0.45
            and native_metrics["chars"] < 600
            and tesseract_available()
        ):
            ocr_text = ocr_page(page, dpi=dpi)
            ocr_metrics = text_metrics(ocr_text)
            if use_ocr or ocr_metrics["quality_score"] >= native_metrics["quality_score"]:
                selected_text = ocr_text
                selected_source = "ocr"
                selected_metrics = ocr_metrics

        extraction_counts[selected_source] = extraction_counts.get(selected_source, 0) + 1
        pages.append(
            {
                "page": page_index + 1,
                "text": selected_text,
                "text_source": selected_source,
                "metrics": selected_metrics,
            }
        )

        if (page_index + 1) % 25 == 0 or page_index + 1 == len(doc):
            print(
                f"[extract] {spec.slug}: {page_index + 1}/{len(doc)} pages "
                f"({selected_source})",
                flush=True,
            )

    pdf_metadata = {
        key: value for key, value in (doc.metadata or {}).items() if value not in (None, "")
    }
    return pages, {"page_count": len(doc), "pdf_metadata": pdf_metadata, "extraction_counts": extraction_counts}


def split_page_units(pages: list[dict]) -> list[dict]:
    units: list[dict] = []
    for page in pages:
        text = page["text"]
        if not text:
            continue
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if len(paragraphs) <= 1:
            paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
        for paragraph in paragraphs:
            units.append(
                {
                    "page": page["page"],
                    "text": paragraph,
                    "text_source": page["text_source"],
                }
            )
    return units


def estimate_tokens(text: str) -> int:
    # Conservative multilingual approximation for chunk sizing metadata.
    return max(1, int(len(text) / 3.8))


def extract_article_refs(text: str) -> list[str]:
    refs = []
    seen = set()
    for match in ARTICLE_RE.finditer(text):
        ref = re.sub(r"\s+", " ", match.group(0)).strip(" .،؛:")
        if ref and ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


def extract_headings(text: str) -> list[str]:
    headings = []
    seen = set()
    for line in text.splitlines():
        line = line.strip()
        if HEADING_RE.match(line):
            clean = line[:140]
            if clean not in seen:
                headings.append(clean)
                seen.add(clean)
    return headings[:12]


def chunk_pages(
    pages: list[dict],
    spec: SectorSpec,
    target_chars: int,
    overlap_chars: int,
) -> list[dict]:
    units = split_page_units(pages)
    chunks: list[dict] = []
    current: list[dict] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        chunk_text = normalize_text("\n\n".join(unit["text"] for unit in current))
        if not chunk_text:
            current = []
            current_chars = 0
            return
        page_start = min(unit["page"] for unit in current)
        page_end = max(unit["page"] for unit in current)
        sources = {}
        for unit in current:
            sources[unit["text_source"]] = sources.get(unit["text_source"], 0) + 1
        chunk_index = len(chunks)
        chunk_id = f"{spec.slug}:{Path(spec.source_pdf).stem}:chunk-{chunk_index:05d}"
        chunks.append(
            {
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "sector": spec.slug,
                "legal_sector": spec.legal_sector,
                "legal_sector_ar": spec.legal_sector_ar,
                "country": "Morocco",
                "language": "ar",
                "source_file": spec.source_pdf,
                "source_title": spec.title,
                "source_title_ar": spec.title_ar,
                "page_start": page_start,
                "page_end": page_end,
                "article_refs": extract_article_refs(chunk_text),
                "headings": extract_headings(chunk_text),
                "text_source_counts": sources,
                "token_estimate": estimate_tokens(chunk_text),
                "metrics": text_metrics(chunk_text),
                "text": chunk_text,
            }
        )
        overlap: list[dict] = []
        chars = 0
        for unit in reversed(current):
            if chars >= overlap_chars:
                break
            overlap.insert(0, unit)
            chars += len(unit["text"])
        current = overlap
        current_chars = sum(len(unit["text"]) for unit in current)

    for unit in units:
        text = unit["text"]
        is_article_start = bool(ARTICLE_RE.match(text.strip()))
        if current and is_article_start and current_chars >= max(600, target_chars // 3):
            flush()
        if current and current_chars + len(text) + 2 > target_chars:
            flush()
        current.append(unit)
        current_chars += len(text) + 2
    flush()

    return chunks


def load_chunks(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_embeddings(sector_dirs: list[Path], model_name: str, batch_size: int) -> dict:
    from sentence_transformers import SentenceTransformer

    print(f"[embed] loading {model_name} from local cache", flush=True)
    model = SentenceTransformer(model_name, local_files_only=True)
    dimension = model.get_sentence_embedding_dimension()
    summary = {
        "model": model_name,
        "dimension": dimension,
        "normalized": True,
        "sectors": {},
    }

    for sector_dir in sector_dirs:
        chunks_path = sector_dir / "chunks.jsonl"
        chunks = load_chunks(chunks_path)
        texts = [
            (
                f"passage: {chunk['legal_sector']} | {chunk['source_title_ar']}\n"
                f"pages {chunk['page_start']}-{chunk['page_end']}\n{chunk['text']}"
            )
            for chunk in chunks
        ]
        print(f"[embed] {sector_dir.name}: {len(texts)} chunks", flush=True)
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=True,
        ).astype("float32")
        np.save(sector_dir / "embeddings.npy", embeddings)
        embedding_meta = {
            "model": model_name,
            "dimension": int(embeddings.shape[1]) if embeddings.ndim == 2 else dimension,
            "chunk_count": int(embeddings.shape[0]),
            "normalized": True,
            "row_alignment": "embeddings.npy row N corresponds to chunks.jsonl line N",
            "query_prefix": "query: ",
            "passage_prefix": "passage: ",
        }
        write_json(sector_dir / "embeddings_meta.json", embedding_meta)
        summary["sectors"][sector_dir.name] = embedding_meta

    return summary


def build_agent_registry(output_dir: Path, manifest: dict) -> dict:
    agents = []
    for sector in manifest["sectors"]:
        spec = next(item for item in SECTORS if item.slug == sector["slug"])
        agents.append(
            {
                "agent_id": spec.agent_id,
                "sector": spec.slug,
                "legal_sector": spec.legal_sector,
                "legal_sector_ar": spec.legal_sector_ar,
                "scope": spec.agent_scope,
                "dataset": f"sectors/{spec.slug}/chunks.jsonl",
                "pages": f"sectors/{spec.slug}/pages.jsonl",
                "embeddings": f"sectors/{spec.slug}/embeddings.npy",
                "embedding_metadata": f"sectors/{spec.slug}/embeddings_meta.json",
                "source_pdf": spec.source_pdf,
                "system_prompt": (
                    "You are a small Moroccan legal-domain assistant. "
                    f"Only answer questions inside this scope: {spec.agent_scope} "
                    "Use retrieved passages from this sector dataset first. "
                    "Cite chunk_id and page_start/page_end for every legal claim. "
                    "If the retrieved context is weak, missing, or outside scope, say so and route to another sector agent."
                ),
            }
        )
    registry = {
        "version": "1.0",
        "built_at": manifest["built_at"],
        "router_policy": (
            "Route each question to exactly one sector first. Use cross-sector retrieval only "
            "when the user explicitly asks a mixed-domain question."
        ),
        "agents": agents,
    }
    write_json(output_dir / "agent_registry.json", registry)
    return registry


def build_readme(output_dir: Path, manifest: dict) -> None:
    lines = [
        "# Moroccan Legal RAG Datasets",
        "",
        "This directory contains sector-separated RAG datasets generated from the local PDFs.",
        "",
        "## Structure",
        "",
        "- `manifest.json`: global build/source summary.",
        "- `agent_registry.json`: router and tiny expert-agent configuration.",
        "- `sectors/<sector>/pages.jsonl`: one extracted page per line.",
        "- `sectors/<sector>/chunks.jsonl`: retrieval chunks with source, page, article, and quality metadata.",
        "- `sectors/<sector>/embeddings.npy`: normalized dense embeddings aligned to `chunks.jsonl` line numbers.",
        "- `sectors/<sector>/embeddings_meta.json`: embedding model and alignment metadata.",
        "",
        "## Sectors",
        "",
    ]
    for sector in manifest["sectors"]:
        lines.append(
            f"- `{sector['slug']}`: {sector['legal_sector']} from `{sector['source_file']}` "
            f"({sector['page_count']} pages, {sector['chunk_count']} chunks, extraction: {sector['extraction_counts']})."
        )
    lines.extend(
        [
            "",
            "## Retrieval Contract",
            "",
            "Each `chunks.jsonl` record includes `chunk_id`, `sector`, `legal_sector`, `source_file`, "
            "`page_start`, `page_end`, `article_refs`, `headings`, `metrics`, and `text`.",
            "",
            "For dense retrieval with BGE-M3, encode user questions with the `query: ` prefix, "
            "load the sector `embeddings.npy`, and rank with cosine similarity. The embeddings are already normalized, "
            "so a dot product is cosine similarity.",
            "",
            "```python",
            "import json, numpy as np",
            "from sentence_transformers import SentenceTransformer",
            "",
            "sector = 'criminal_law'",
            "base = f'rag_datasets/sectors/{sector}'",
            "chunks = [json.loads(line) for line in open(f'{base}/chunks.jsonl', encoding='utf-8')]",
            "emb = np.load(f'{base}/embeddings.npy')",
            "model = SentenceTransformer('BAAI/bge-m3', local_files_only=True)",
            "q = model.encode(['query: ما عقوبة السرقة؟'], normalize_embeddings=True)",
            "top = np.argsort(emb @ q[0])[-5:][::-1]",
            "for i in top:",
            "    print(chunks[i]['chunk_id'], chunks[i]['page_start'], chunks[i]['page_end'])",
            "    print(chunks[i]['text'][:500])",
            "```",
            "",
            "## Notes",
            "",
            "The criminal-law PDF uses a legacy font encoding, so that sector was OCRed with Arabic Tesseract. "
            "Other sectors use native PDF text extraction unless a page has very weak native text.",
            "",
            "These datasets preserve source page references for retrieval and citation. They are not a substitute for checking the official legal text.",
            "",
        ]
    )
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chunk-chars", type=int, default=2200)
    parser.add_argument("--overlap-chars", type=int, default=280)
    parser.add_argument("--ocr-dpi", type=int, default=220)
    parser.add_argument("--no-ocr-low-quality", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument("--embedding-model", default="BAAI/bge-m3")
    parser.add_argument("--embedding-batch-size", type=int, default=8)
    args = parser.parse_args()

    output_dir = args.output.resolve()
    sectors_dir = output_dir / "sectors"
    sectors_dir.mkdir(parents=True, exist_ok=True)
    built_at = now_utc()

    manifest = {
        "version": "1.0",
        "built_at": built_at,
        "source_root": str(ROOT),
        "output_dir": str(output_dir),
        "chunking": {
            "target_chars": args.chunk_chars,
            "overlap_chars": args.overlap_chars,
        },
        "sectors": [],
    }
    sector_dirs: list[Path] = []

    for spec in SECTORS:
        start = time.time()
        pdf_path = ROOT / spec.source_pdf
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)
        sector_dir = sectors_dir / spec.slug
        sector_dir.mkdir(parents=True, exist_ok=True)
        sector_dirs.append(sector_dir)

        print(f"[sector] {spec.slug}: {spec.source_pdf}", flush=True)
        pages, extraction_meta = extract_pages(
            pdf_path,
            spec,
            dpi=args.ocr_dpi,
            ocr_low_quality=not args.no_ocr_low_quality,
        )
        chunks = chunk_pages(
            pages,
            spec,
            target_chars=args.chunk_chars,
            overlap_chars=args.overlap_chars,
        )

        pages_count = write_jsonl(sector_dir / "pages.jsonl", pages)
        chunks_count = write_jsonl(sector_dir / "chunks.jsonl", chunks)
        total_chars = sum(chunk["metrics"]["chars"] for chunk in chunks)
        sector_meta = {
            "slug": spec.slug,
            "legal_sector": spec.legal_sector,
            "legal_sector_ar": spec.legal_sector_ar,
            "source_file": spec.source_pdf,
            "source_sha256": sha256_file(pdf_path),
            "source_title": spec.title,
            "source_title_ar": spec.title_ar,
            "country": "Morocco",
            "language": "ar",
            "extraction_mode": spec.extraction_mode,
            "extraction_counts": extraction_meta["extraction_counts"],
            "page_count": extraction_meta["page_count"],
            "pages_jsonl_count": pages_count,
            "chunk_count": chunks_count,
            "total_chunk_chars": total_chars,
            "pdf_metadata": extraction_meta["pdf_metadata"],
            "built_at": built_at,
            "build_seconds": round(time.time() - start, 2),
        }
        write_json(sector_dir / "metadata.json", sector_meta)
        manifest["sectors"].append(sector_meta)
        print(
            f"[sector] {spec.slug}: wrote {pages_count} pages, {chunks_count} chunks",
            flush=True,
        )

    if not args.skip_embeddings:
        try:
            manifest["embeddings"] = build_embeddings(
                sector_dirs,
                model_name=args.embedding_model,
                batch_size=args.embedding_batch_size,
            )
        except Exception as exc:
            manifest["embeddings_error"] = repr(exc)
            print(f"[embed] skipped after error: {exc!r}", flush=True)

    write_json(output_dir / "manifest.json", manifest)
    build_agent_registry(output_dir, manifest)
    build_readme(output_dir, manifest)
    print(f"[done] wrote {output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
