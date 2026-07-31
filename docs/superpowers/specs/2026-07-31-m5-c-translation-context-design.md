# M5-C Limited Translation Context Design

**Date:** 2026-07-31

## Goal

Improve terminology and paragraph coherence without uploading a PDF file, batching the whole paper
into one request, or adding retrieval infrastructure. Each provider request still translates one
protected `TextFlow` and returns normal and compact candidates.

## Request context

For each translatable flow, PaperTrans deterministically supplies:

- `region_type`;
- the nearest active title or heading, capped at 200 characters;
- the immediately previous translatable flow, capped at 600 characters;
- the immediately following translatable flow, capped at 600 characters;
- only glossary entries whose source term occurs in the current flow.

Whitespace is normalized before clipping. Context is advisory: providers must translate only the
current protected `source_text`, must not copy neighboring paragraphs into the result, and must
preserve every current-segment placeholder exactly once.

## Glossary

The CLI accepts an optional `--glossary <path>` JSON object:

```json
{
  "region proposal": "候选区域",
  "intersection over union": "交并比"
}
```

Keys and values must be non-empty strings. Files are limited to 500 entries and each side to 200
characters. Invalid files fail before provider creation. The glossary path and full glossary are
not written to job artifacts; reports contain counts only.

## Cache and privacy

The existing provider cache key already hashes request context. Changing a relevant heading,
neighbor, glossary term, or prompt version therefore causes a cache miss for the affected segment
without placing context text in cache metadata. API keys remain excluded.

`translation-report.json` records only aggregate context coverage: flow count, heading coverage,
neighbor coverage, glossary term count, and clipping counts. It does not persist neighboring text.

## Deferred

M5-C does not add embeddings, vector search, whole-document prompts, automatic terminology mining,
cross-segment provider batches, GUI glossary editing, OCR, or model downloads.

## Completion gate

- Context construction is deterministic and bounded.
- Distant paragraphs never enter a request.
- Prompt output makes the current segment/context boundary explicit.
- Relevant glossary or neighbor changes invalidate only matching cache requests.
- Existing protection, provider reliability, layout, and PDF quality tests remain green.
