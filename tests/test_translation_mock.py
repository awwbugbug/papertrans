from papertrans.translation import MockTranslationProvider, TranslationRequest


def test_mock_translation_is_deterministic_and_compact() -> None:
    provider = MockTranslationProvider(length_factor=1.2)

    result = provider.translate([TranslationRequest(segment_id="s1", text="hello world")])[0]

    assert result.provider == "mock"
    assert result.normal
    assert result.compact
    assert any("\u4e00" <= character <= "\u9fff" for character in result.normal)
    assert len(result.compact) < len(result.normal)
