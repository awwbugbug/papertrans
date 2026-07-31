import json

from papertrans.translation import TranslationRequest, TranslationUsage, prompt
from papertrans.translation.profiles import DEEPSEEK_PROFILE, KIMI_PROFILE
from papertrans.translation.prompt import PROMPT_VERSION, build_chat_messages


def test_named_profiles_use_current_official_defaults() -> None:
    assert DEEPSEEK_PROFILE.chat_url == "https://api.deepseek.com/chat/completions"
    assert DEEPSEEK_PROFILE.default_model == "deepseek-v4-flash"
    assert DEEPSEEK_PROFILE.api_key_env == "DEEPSEEK_API_KEY"
    assert DEEPSEEK_PROFILE.request_overrides == {"thinking": {"type": "disabled"}}
    assert KIMI_PROFILE.chat_url == "https://api.moonshot.cn/v1/chat/completions"
    assert KIMI_PROFILE.default_model == "kimi-k2.6"
    assert KIMI_PROFILE.api_key_env == "MOONSHOT_API_KEY"


def test_profiles_estimate_native_currency_cost() -> None:
    usage = TranslationUsage(
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=100_000,
    )
    assert DEEPSEEK_PROFILE.pricing is not None
    assert DEEPSEEK_PROFILE.pricing.estimate(usage) == 0.1337
    assert DEEPSEEK_PROFILE.pricing.currency == "USD"
    assert KIMI_PROFILE.pricing is not None
    assert KIMI_PROFILE.pricing.estimate(usage) == 7.85
    assert KIMI_PROFILE.pricing.currency == "CNY"


def test_cache_identity_uses_current_prompt_version(monkeypatch) -> None:
    monkeypatch.setattr(prompt, "PROMPT_VERSION", "academic_pdf_zh_v2")

    identity = DEEPSEEK_PROFILE.cache_identity(DEEPSEEK_PROFILE.default_model)

    assert identity["prompt_version"] == "academic_pdf_zh_v2"


def test_prompt_is_versioned_and_carries_only_limited_segment_context() -> None:
    request = TranslationRequest(
        segment_id="flow-1",
        text="See 鉄T0001鉄?in 10 ms.",
        protected_tokens=("鉄T0001鉄?", "鉄T0002鉄?"),
        context={
            "schema_version": "m5c_v1",
            "region_type": "paragraph",
            "section_title": "Methods",
            "previous_text": "Previous paragraph.",
            "next_text": "Next paragraph.",
            "glossary": [{"source": "proposal", "target": "候选区域"}],
        },
    )
    messages = build_chat_messages(request)
    payload = json.loads(messages[1]["content"])
    assert PROMPT_VERSION == "academic_pdf_zh_v2"
    assert [message["role"] for message in messages] == ["system", "user"]
    assert payload == {
        "source_language": "en",
        "target_language": "zh-CN",
        "protected_tokens": ["鉄T0001鉄?", "鉄T0002鉄?"],
        "segment_context": {
            "glossary": [{"source": "proposal", "target": "候选区域"}],
            "next_text": "Next paragraph.",
            "previous_text": "Previous paragraph.",
            "region_type": "paragraph",
            "schema_version": "m5c_v1",
            "section_title": "Methods",
        },
        "source_text": "See 鉄T0001鉄?in 10 ms.",
    }
    assert "normal" in messages[0]["content"]
    assert "compact" in messages[0]["content"]
    assert "JSON" in messages[0]["content"]
    assert "current segment" in messages[0]["content"]
    assert "neighboring context" in messages[0]["content"]
