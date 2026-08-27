import json

from papertrans.domain import (
    BoundingBox,
    Document,
    Page,
    Region,
    RegionType,
    TextFlow,
    TextStyle,
)
from papertrans.layout.cjk import _take_line
from papertrans.layout.cjk_font import CJKFontResolver, is_word_segmented
from papertrans.translation import TranslationRequest, TranslationResult
from papertrans.translation.pipeline import translate_text_flows_with_protection
from papertrans.translation.prompt import build_chat_messages, target_language_name


def _document_with_flow(width: float = 240, height: float = 140) -> Document:
    region = Region(
        id="p1-text-1",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(50, 100, 50 + width, 100 + height),
        source_text="Source paragraph text.",
        style=TextStyle(font_name="Times", font_size=10, color=0),
        reading_order=1,
    )
    flow = TextFlow(
        id="flow-p1-text-1",
        type=RegionType.PARAGRAPH,
        region_ids=[region.id],
        page_numbers=[1],
        raw_text=region.source_text,
        source_text=region.source_text,
        translatable=True,
    )
    return Document(
        source_path="fixture.pdf",
        pages=[Page(number=1, width=600, height=800, regions=[region])],
        text_flows=[flow],
    )


class _SpyProvider:
    name = "spy"
    cache_identity = {"provider": "spy"}

    def __init__(self) -> None:
        self.requests: list[TranslationRequest] = []

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        self.requests = list(requests)
        return [
            TranslationResult(
                segment_id=request.segment_id, normal="x", compact=None, provider="spy"
            )
            for request in requests
        ]


def test_target_language_name_maps_supported_codes() -> None:
    assert target_language_name("zh-CN") == "Simplified Chinese"
    assert target_language_name("en") == "English"
    assert target_language_name("ja") == "Japanese"
    assert target_language_name("ko") == "Korean"
    assert target_language_name("fr") == "French"
    assert target_language_name("es") == "Spanish"
    assert target_language_name("de") == "German"
    assert target_language_name("ru") == "Russian"


def test_segment_prompt_names_selected_target_language() -> None:
    for code, name in [("en", "English"), ("ja", "Japanese"), ("ru", "Russian")]:
        request = TranslationRequest(segment_id="flow-1", text="Hello.", target_language=code)
        messages = build_chat_messages(request)
        system = messages[0]["content"]
        assert f"into {name}." in system
        assert "Simplified Chinese" not in system
        # Payload keeps the raw code for the model and the cache key.
        assert json.loads(messages[1]["content"])["target_language"] == code


def test_default_prompt_still_targets_simplified_chinese() -> None:
    request = TranslationRequest(segment_id="flow-1", text="Hello.")
    system = build_chat_messages(request)[0]["content"]
    assert "into Simplified Chinese." in system


def test_text_prompt_names_selected_target_language() -> None:
    request = TranslationRequest(
        segment_id="flow-1",
        text="Hello.",
        target_language="fr",
        context={"translation_mode": "standalone_text"},
    )
    system = build_chat_messages(request)[0]["content"]
    assert "into French." in system
    assert "supplied text" in system


def test_word_segmentation_flags_space_delimited_languages() -> None:
    assert is_word_segmented("en") is True
    assert is_word_segmented("fr") is True
    assert is_word_segmented("ru") is True
    assert is_word_segmented("ko") is True
    assert is_word_segmented("zh-CN") is False
    assert is_word_segmented("ja") is False


def test_supported_languages_resolve_to_local_fonts() -> None:
    for language in ("zh-CN", "en", "ja", "ko", "fr", "es", "de", "ru"):
        resolved = CJKFontResolver(language).resolve()
        assert resolved.path.is_file()
        assert resolved.metrics is not None


def test_word_line_breaking_stops_on_word_boundaries() -> None:
    font = CJKFontResolver("en").resolve()
    size = 10.0
    text = "alpha beta gamma delta"
    width = font.metrics.text_length("alpha beta", fontsize=size) + 2.0
    assert font.metrics.text_length("alpha beta gamma", fontsize=size) > width

    line, remaining = _take_line(text, width, font, size, word_segmented=True)
    assert line == "alpha beta"
    assert remaining.strip().startswith("gamma")


def test_over_long_word_falls_back_to_character_breaking() -> None:
    font = CJKFontResolver("en").resolve()
    size = 10.0
    word = "supercalifragilisticexpialidocious"
    width = font.metrics.text_length("super", fontsize=size) + 1.0

    line, remaining = _take_line(word, width, font, size, word_segmented=True)
    assert line
    assert remaining
    assert word.startswith(line)
    assert word == line + remaining


def test_translation_pipeline_propagates_target_language() -> None:
    document = _document_with_flow()
    spy = _SpyProvider()

    translate_text_flows_with_protection(document, spy, target_language="fr")

    assert spy.requests
    assert all(request.target_language == "fr" for request in spy.requests)
