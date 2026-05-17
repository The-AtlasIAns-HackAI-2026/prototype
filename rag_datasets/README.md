# Moroccan Legal RAG Datasets

This directory contains sector-separated RAG datasets generated from the local PDFs.

## Structure

- `manifest.json`: global build/source summary.
- `agent_registry.json`: router and tiny expert-agent configuration.
- `sectors/<sector>/pages.jsonl`: one extracted page per line.
- `sectors/<sector>/chunks.jsonl`: retrieval chunks with source, page, article, and quality metadata.
- `sectors/<sector>/embeddings.npy`: normalized dense embeddings aligned to `chunks.jsonl` line numbers.
- `sectors/<sector>/embeddings_meta.json`: embedding model and alignment metadata.

## Sectors

- `family_law`: Family law from `family-law-morocco.pdf` (91 pages, 65 chunks, extraction: {'native': 91}).
- `constitutional_law`: Constitutional law from `constitution.pdf` (82 pages, 57 chunks, extraction: {'native': 82}).
- `civil_procedure`: Civil procedure from `civil.pdf` (155 pages, 149 chunks, extraction: {'native': 155}).
- `criminal_law`: Criminal law from `criminal-laws.pdf` (219 pages, 430 chunks, extraction: {'ocr': 219}).
- `public_finance`: Public finance and tax law from `finance-project-2026.pdf` (93 pages, 116 chunks, extraction: {'native': 84, 'ocr': 9}).

## Retrieval Contract

Each `chunks.jsonl` record includes `chunk_id`, `sector`, `legal_sector`, `source_file`, `page_start`, `page_end`, `article_refs`, `headings`, `metrics`, and `text`.

For dense retrieval with BGE-M3, encode user questions with the `query: ` prefix, load the sector `embeddings.npy`, and rank with cosine similarity. The embeddings are already normalized, so a dot product is cosine similarity.

```python
import json, numpy as np
from sentence_transformers import SentenceTransformer

sector = 'criminal_law'
base = f'rag_datasets/sectors/{sector}'
chunks = [json.loads(line) for line in open(f'{base}/chunks.jsonl', encoding='utf-8')]
emb = np.load(f'{base}/embeddings.npy')
model = SentenceTransformer('BAAI/bge-m3', local_files_only=True)
q = model.encode(['query: ما عقوبة السرقة؟'], normalize_embeddings=True)
top = np.argsort(emb @ q[0])[-5:][::-1]
for i in top:
    print(chunks[i]['chunk_id'], chunks[i]['page_start'], chunks[i]['page_end'])
    print(chunks[i]['text'][:500])
```

## Notes

The criminal-law PDF uses a legacy font encoding, so that sector was OCRed with Arabic Tesseract. Other sectors use native PDF text extraction unless a page has very weak native text.

These datasets preserve source page references for retrieval and citation. They are not a substitute for checking the official legal text.
