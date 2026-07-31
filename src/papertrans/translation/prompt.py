from __future__ import annotations

import json

from papertrans.translation.base import TranslationRequest

PROMPT_VERSION = "academic_pdf_zh_v2"
SYSTEM_PROMPT = (
    "Translate one protected academic-paper segment into Simplified Chinese. "
    "Translate only the current segment; use the section title and neighboring context only "
    "for terminology and coherence, and never copy neighboring context into the translation. "
    "Follow relevant glossary entries exactly. "
    "Preserve every listed placeholder exactly once and unchanged. Preserve all claims, "
    "citations, variables, units, and technical meaning. Return JSON only, with exactly two "
    "string fields: normal for the complete natural translation and compact for an equally "
    "complete but more concise layout candidate."
)


def build_chat_messages(request: TranslationRequest) -> list[dict[str, str]]:
    payload = {
        "source_language": request.source_language,
        "target_language": request.target_language,
        "protected_tokens": list(request.protected_tokens),
        "segment_context": request.context,
        "source_text": request.text,
    }
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]
