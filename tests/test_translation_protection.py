import pytest

from papertrans.domain import Document, RegionType, TextFlow
from papertrans.translation import (
    ProtectedTokenError,
    TranslationRequest,
    TranslationResult,
    placeholder_issues,
    protect_text,
    restore_text,
    translate_text_flows_with_protection,
)


def test_placeholder_issues_reports_missing_duplicated_and_unknown_tokens() -> None:
    expected = ("⟦PT0001⟧", "⟦PT0002⟧", "⟦PT0003⟧")

    issues = placeholder_issues(
        "译文⟦PT0001⟧⟦PT0001⟧⟦PT0003⟧⟦PT9999⟧",
        expected,
    )

    assert issues == (("⟦PT0002⟧",), ("⟦PT0001⟧",), ("⟦PT9999⟧",))


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


def test_pipeline_passes_bounded_context_and_relevant_glossary_to_provider() -> None:
    class CapturingProvider:
        name = "capturing"

        def __init__(self) -> None:
            self.requests: list[TranslationRequest] = []

        def translate(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
            self.requests.extend(requests)
            return [
                TranslationResult(
                    segment_id=request.segment_id,
                    normal=request.text,
                    compact=request.text,
                    provider=self.name,
                )
                for request in requests
            ]

    flows = [
        TextFlow(
            id="heading",
            type=RegionType.HEADING,
            region_ids=["heading-region"],
            page_numbers=[1],
            raw_text="2. Methods",
            source_text="2. Methods",
            translatable=True,
        ),
        TextFlow(
            id="first",
            type=RegionType.PARAGRAPH,
            region_ids=["first-region"],
            page_numbers=[1],
            raw_text="A region proposal is generated.",
            source_text="A region proposal is generated.",
            translatable=True,
        ),
        TextFlow(
            id="second",
            type=RegionType.PARAGRAPH,
            region_ids=["second-region"],
            page_numbers=[1],
            raw_text="The detector consumes it.",
            source_text="The detector consumes it.",
            translatable=True,
        ),
    ]
    provider = CapturingProvider()

    batch = translate_text_flows_with_protection(
        Document(source_path="fixture.pdf", text_flows=flows),
        provider,
        glossary={"region proposal": "候选区域", "detector": "检测器"},
    )

    request_by_id = {request.segment_id: request for request in provider.requests}
    assert request_by_id["first"].context["section_title"] == "2. Methods"
    assert request_by_id["first"].context["previous_text"] == "2. Methods"
    assert request_by_id["first"].context["next_text"] == "The detector consumes it."
    assert request_by_id["first"].context["glossary"] == [
        {"source": "region proposal", "target": "候选区域"}
    ]
    assert batch.context_stats.glossary_term_count == 2
