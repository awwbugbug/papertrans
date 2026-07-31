import pytest

from papertrans.domain import Document, RegionType, TextFlow
from papertrans.translation import (
    ProtectedTokenError,
    TranslationRequest,
    TranslationResult,
    protect_text,
    restore_text,
    translate_text_flows_with_protection,
)


def test_protect_and_restore_academic_tokens_exactly() -> None:
    source = (
        "See [12, 14-16], DOI 10.1000/xyz.123, https://example.org/a, "
        "x_i, λ, 10 ms and 95%."
    )

    segment = protect_text("flow-1", source)

    assert [token.kind for token in segment.tokens] == [
        "citation",
        "doi",
        "url",
        "variable",
        "variable",
        "unit",
        "unit",
    ]
    translated = f"中文 {segment.protected_text} 结束"
    restored, validation = restore_text(translated, segment, "normal")
    assert validation.passed is True
    assert source in restored
    assert "⟦PT" not in restored


class _DroppingProvider:
    name = "dropping"

    def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        return [
            TranslationResult(
                segment_id=request.segment_id,
                normal="占位符已丢失",
                provider=self.name,
            )
            for request in requests
        ]


def test_translation_pipeline_rejects_missing_protected_token() -> None:
    flow = TextFlow(
        id="flow-1",
        type=RegionType.PARAGRAPH,
        region_ids=["region-1"],
        page_numbers=[1],
        raw_text="See [1].",
        source_text="See [1].",
        translatable=True,
    )
    document = Document(source_path="fixture.pdf", text_flows=[flow])

    with pytest.raises(ProtectedTokenError) as exc_info:
        translate_text_flows_with_protection(document, _DroppingProvider())

    assert exc_info.value.validation.missing == ("⟦PT0001⟧",)


def test_restore_reports_duplicate_and_unknown_placeholders() -> None:
    segment = protect_text("flow-1", "See [1].")
    placeholder = segment.tokens[0].placeholder

    _, validation = restore_text(
        f"中文{placeholder}{placeholder}⟦PT9999⟧",
        segment,
        "normal",
    )

    assert validation.passed is False
    assert validation.duplicated == (placeholder,)
    assert validation.unknown == ("⟦PT9999⟧",)
