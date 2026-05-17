# Hotline Datasets

These files are placeholders for the vetted bureaucracy and legal hotline datasets.

Each expert in `config/hotline/experts.json` points to one JSONL file here. Replace the placeholder records with curated, sourced, jurisdiction-specific content before using the assistant for real legal or administrative guidance.

Recommended JSONL shape:

```json
{
  "id": "unique-record-id",
  "jurisdiction": "MA",
  "topic": "short topic",
  "source_title": "official or vetted source title",
  "source_url": "https://example.gov.ma/source",
  "updated_at": "2026-05-17",
  "content": "short factual guidance",
  "risk_level": "low|medium|high",
  "human_review_required": false
}
```

Keep secrets and private citizen data out of this directory.
