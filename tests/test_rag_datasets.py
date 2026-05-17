from __future__ import annotations

import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = ROOT / "rag_datasets"

REQUIRED_CHUNK_FIELDS = {
    "chunk_id",
    "chunk_index",
    "sector",
    "legal_sector",
    "legal_sector_ar",
    "country",
    "language",
    "source_file",
    "source_title",
    "source_title_ar",
    "page_start",
    "page_end",
    "article_refs",
    "headings",
    "text_source_counts",
    "token_estimate",
    "metrics",
    "text",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def retrieve_by_embedding(
    query_embedding: np.ndarray,
    embeddings: np.ndarray,
    chunks: list[dict],
    top_k: int = 5,
) -> list[tuple[float, dict]]:
    scores = embeddings @ query_embedding
    top_indices = np.argsort(scores)[-top_k:][::-1]
    return [(float(scores[index]), chunks[int(index)]) for index in top_indices]


def test_agent_registry_covers_manifest_sectors() -> None:
    manifest_path = DATASET_ROOT / "manifest.json"
    registry_path = DATASET_ROOT / "agent_registry.json"

    assert manifest_path.exists(), "missing RAG manifest"
    assert registry_path.exists(), "missing RAG agent registry"

    manifest = read_json(manifest_path)
    registry = read_json(registry_path)
    manifest_sectors = {sector["slug"] for sector in manifest["sectors"]}
    registry_sectors = {agent["sector"] for agent in registry["agents"]}

    assert manifest["version"] == "1.0"
    assert registry["version"] == manifest["version"]
    assert registry["built_at"] == manifest["built_at"]
    assert registry_sectors == manifest_sectors

    for agent in registry["agents"]:
        assert agent["system_prompt"]
        assert "Cite chunk_id" in agent["system_prompt"]
        assert agent["source_pdf"]
        assert (ROOT / agent["source_pdf"]).exists()

        for key in ("dataset", "pages", "embeddings", "embedding_metadata"):
            path = DATASET_ROOT / agent[key]
            assert path.exists(), f"{agent['sector']} missing {key}: {path}"


def test_chunks_match_manifest_counts_and_required_metadata() -> None:
    manifest = read_json(DATASET_ROOT / "manifest.json")

    for sector_meta in manifest["sectors"]:
        sector = sector_meta["slug"]
        sector_dir = DATASET_ROOT / "sectors" / sector
        chunks = read_jsonl(sector_dir / "chunks.jsonl")
        pages = read_jsonl(sector_dir / "pages.jsonl")
        metadata = read_json(sector_dir / "metadata.json")

        assert len(chunks) == sector_meta["chunk_count"]
        assert len(pages) == sector_meta["pages_jsonl_count"]
        assert metadata["slug"] == sector
        assert metadata["chunk_count"] == len(chunks)
        assert metadata["pages_jsonl_count"] == len(pages)
        assert metadata["source_sha256"] == sector_meta["source_sha256"]

        for index, chunk in enumerate(chunks):
            assert REQUIRED_CHUNK_FIELDS <= set(chunk)
            assert chunk["chunk_index"] == index
            assert chunk["chunk_id"].startswith(f"{sector}:")
            assert chunk["sector"] == sector
            assert chunk["source_file"] == sector_meta["source_file"]
            assert chunk["country"] == "Morocco"
            assert chunk["language"] == "ar"

            assert 1 <= chunk["page_start"] <= chunk["page_end"]
            assert chunk["page_end"] <= sector_meta["page_count"]
            assert isinstance(chunk["text"], str) and chunk["text"].strip()
            assert isinstance(chunk["article_refs"], list)
            assert isinstance(chunk["headings"], list)
            assert isinstance(chunk["text_source_counts"], dict)
            assert chunk["text_source_counts"]
            assert chunk["token_estimate"] > 0

            metrics = chunk["metrics"]
            assert metrics["chars"] == len(chunk["text"])
            assert metrics["arabic_chars"] > 0
            assert 0 <= metrics["arabic_ratio"] <= 1
            assert 0 <= metrics["quality_score"] <= 1


def test_embeddings_are_aligned_normalized_and_retrievable() -> None:
    manifest = read_json(DATASET_ROOT / "manifest.json")

    assert manifest["embeddings"]["normalized"] is True

    for sector_meta in manifest["sectors"]:
        sector = sector_meta["slug"]
        sector_dir = DATASET_ROOT / "sectors" / sector
        chunks = read_jsonl(sector_dir / "chunks.jsonl")
        embedding_meta = read_json(sector_dir / "embeddings_meta.json")
        embeddings = np.load(sector_dir / "embeddings.npy")

        assert embedding_meta["chunk_count"] == len(chunks)
        assert embedding_meta["normalized"] is True
        assert embedding_meta["query_prefix"] == "query: "
        assert embedding_meta["passage_prefix"] == "passage: "
        assert embeddings.ndim == 2
        assert embeddings.shape == (len(chunks), embedding_meta["dimension"])
        assert np.isfinite(embeddings).all()

        norms = np.linalg.norm(embeddings, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-3)

        sample_indices = {0, len(chunks) // 2, len(chunks) - 1}
        for sample_index in sample_indices:
            results = retrieve_by_embedding(
                query_embedding=embeddings[sample_index],
                embeddings=embeddings,
                chunks=chunks,
                top_k=5,
            )
            top_score, top_chunk = results[0]

            assert top_score >= 0.999
            assert top_chunk["chunk_index"] == sample_index
            assert top_chunk["chunk_id"] == chunks[sample_index]["chunk_id"]
