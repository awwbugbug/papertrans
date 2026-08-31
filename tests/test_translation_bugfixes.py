import httpx

from papertrans.domain import (
    BoundingBox,
    Document,
    Page,
    Region,
    RegionType,
    TextFlow,
    TextStyle,
)
from papertrans.layout.cjk import _size_steps, build_cjk_layout
from papertrans.structure.reading_order import _classify_reference_section
from papertrans.translation import TranslationResult
from papertrans.translation.compatible_client import _error_detail, _http_error
from papertrans.translation.reliability import ProviderExecutionError


def _region(rid, rtype, text, order):
    return Region(
        id=rid,
        type=rtype,
        bbox=BoundingBox(50, 100 + order * 20, 300, 116 + order * 20),
        source_text=text,
        style=TextStyle(font_name="Times", font_size=9, color=0),
        reading_order=order,
        translatable=rtype in {RegionType.PARAGRAPH, RegionType.HEADING},
    )


def test_appendix_after_references_stays_translatable():
    # Bug 2: content after a References heading that starts a new section (appendix)
    # must not be swallowed as reference entries.
    regions = [
        _region("r1", RegionType.HEADING, "References", 1),
        _region("r2", RegionType.PARAGRAPH, "[1] A. Author. A paper. In CVPR, 2020.", 2),
        _region("r3", RegionType.PARAGRAPH, "[2] B. Author. Another. In ICCV, 2021.", 3),
        _region("r4", RegionType.HEADING, "A. Object Detection Baselines", 4),
        _region("r5", RegionType.PARAGRAPH, "In this section we introduce our method.", 5),
        _region("r6", RegionType.PARAGRAPH, "We adopt the baseline system for detection.", 6),
    ]
    document = Document(
        source_path="x.pdf",
        pages=[Page(number=1, width=600, height=800, regions=regions)],
    )
    _classify_reference_section(document)
    by_id = {region.id: region for region in regions}

    # Real reference entries stay non-translatable.
    assert by_id["r2"].type == RegionType.REFERENCE
    assert by_id["r2"].translatable is False
    assert by_id["r3"].type == RegionType.REFERENCE
    # Appendix heading and its body remain translatable content.
    assert by_id["r5"].type == RegionType.PARAGRAPH
    assert by_id["r5"].translatable is True
    assert by_id["r6"].type == RegionType.PARAGRAPH
    assert by_id["r6"].translatable is True


def _single_flow_document(width=150.0, height=90.0):
    region = Region(
        id="p1-text-1",
        type=RegionType.PARAGRAPH,
        bbox=BoundingBox(50, 100, 50 + width, 100 + height),
        source_text="Source paragraph.",
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


def test_word_segmented_layout_uses_lower_font_floor():
    # Bug 1: space-delimited languages get a lower minimum font scale so longer text fits.
    assert min(_size_steps(10.0, 0.60)) < min(_size_steps(10.0, 0.72))

    document = _single_flow_document()
    translation = TranslationResult(
        segment_id="flow-p1-text-1",
        normal="This is a fairly long English paragraph " * 3,
        compact="This is a shorter English paragraph " * 2,
        provider="mock",
    )
    latin = build_cjk_layout(document, {translation.segment_id: translation}, word_segmented=True)
    cjk = build_cjk_layout(document, {translation.segment_id: translation}, word_segmented=False)
    # Space-delimited scripts get the most room; CJK stays a little tighter but still below
    # the old 0.72 so a single long line does not fail the whole document.
    assert latin.stats["minimum_font_scale_floor"] == 0.60
    assert cjk.stats["minimum_font_scale_floor"] == 0.65
    assert latin.stats["minimum_font_scale_floor"] < cjk.stats["minimum_font_scale_floor"] < 0.72


def test_provider_http_error_detail_surfaces_message():
    # Bug 3 UX: the provider's real error (e.g. insufficient balance) reaches the user.
    response = httpx.Response(429, json={"error": {"message": "余额不足或无可用资源包,请充值。"}})
    detail = _error_detail(response)
    assert detail is not None and "余额不足" in detail

    error = _http_error(429, detail)
    assert error.detail == detail

    execution_error = ProviderExecutionError("s0", 1, error)
    assert "余额不足" in str(execution_error)
    assert "HTTP 429" in str(execution_error)


def test_named_provider_falls_back_to_alternate_endpoint_on_plan_mismatch():
    # A key on a different plan (e.g. Zhipu Coding Plan vs pay-as-you-go) makes the primary
    # endpoint answer 429; the provider must transparently try the alternate endpoint.
    from papertrans.translation.base import TranslationRequest
    from papertrans.translation.registry import create_translation_provider

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "coding" in str(request.url):
            return httpx.Response(429, json={"error": {"message": "余额不足或无可用资源包"}})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"normal":"\\u8a33","compact":"\\u8a33"}'},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = create_translation_provider(
        "zhipu", environ={"ZHIPUAI_API_KEY": "test-key"}, http_client=client
    )
    result = provider.translate(
        [TranslationRequest(segment_id="s0", text="hi", target_language="ja")]
    )
    assert result[0].normal == "訳"
    assert any("coding" in url for url in seen)
    assert any(url.endswith("/api/paas/v4/chat/completions") for url in seen)


def test_error_detail_redacts_secret_like_content():
    response = httpx.Response(
        401, json={"error": {"message": "Invalid credential sk-abcdef123456"}}
    )
    detail = _error_detail(response)
    assert detail is not None
    assert "sk-abcdef123456" not in detail
    assert "[REDACTED]" in detail
