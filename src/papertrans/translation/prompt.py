from __future__ import annotations

import json

from papertrans.translation.base import TranslationRequest

PROMPT_VERSION = "academic_pdf_zh_v2"
TEXT_PROMPT_VERSION = "standalone_text_zh_v1"
SELECTION_PROMPT_VERSION = "selected_text_zh_v1"

DEFAULT_TARGET_LANGUAGE = "zh-CN"

# Human-readable names handed to the model. The cache key already distinguishes
# target languages (see ReliableTranslationProvider._cache_key), so the prompt
# version constants above stay stable across languages.
_TARGET_LANGUAGE_NAMES = {
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "ru": "Russian",
    "pt": "Portuguese",
}


def target_language_name(code: str) -> str:
    """Map a target-language code to the name used inside the system prompt."""
    normalized = (code or "").strip()
    if normalized in _TARGET_LANGUAGE_NAMES:
        return _TARGET_LANGUAGE_NAMES[normalized]
    lowered = normalized.lower()
    if lowered in _TARGET_LANGUAGE_NAMES:
        return _TARGET_LANGUAGE_NAMES[lowered]
    return normalized or _TARGET_LANGUAGE_NAMES[DEFAULT_TARGET_LANGUAGE]


def _segment_system_prompt(language_name: str) -> str:
    return (
        f"Translate one protected academic-paper segment into {language_name}. "
        "Translate only the current segment; use the section title and neighboring context only "
        "for terminology and coherence, and never copy neighboring context into the translation. "
        "Follow relevant glossary entries exactly. "
        "Preserve every listed placeholder exactly once and unchanged. Preserve all claims, "
        "citations, variables, units, and technical meaning. Return JSON only, with exactly two "
        "string fields: normal for the complete natural translation and compact for an equally "
        "complete but more concise layout candidate."
    )


def _text_system_prompt(language_name: str) -> str:
    return (
        f"Translate the current protected text into {language_name}. "
        "Translate only the supplied text. Preserve every listed placeholder exactly once and "
        "unchanged, and preserve all claims, citations, variables, units, URLs, and technical "
        "meaning. Return JSON only, with exactly two string fields: normal for the complete "
        "natural translation and compact for an equally complete but more concise alternative."
    )


# Backwards-compatible module constants describing the default (Simplified Chinese) prompts.
SYSTEM_PROMPT = _segment_system_prompt(_TARGET_LANGUAGE_NAMES[DEFAULT_TARGET_LANGUAGE])
TEXT_SYSTEM_PROMPT = _text_system_prompt(_TARGET_LANGUAGE_NAMES[DEFAULT_TARGET_LANGUAGE])


def build_chat_messages(request: TranslationRequest) -> list[dict[str, str]]:
    language_name = target_language_name(request.target_language)
    is_standalone_text = request.context.get("translation_mode") in {
        "standalone_text",
        "selected_text",
    }
    system_prompt = (
        _text_system_prompt(language_name)
        if is_standalone_text
        else _segment_system_prompt(language_name)
    )
    payload = {
        "source_language": request.source_language,
        "target_language": request.target_language,
        "protected_tokens": list(request.protected_tokens),
        "segment_context": request.context,
        "source_text": request.text,
    }
    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    ]
