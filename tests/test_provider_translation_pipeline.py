import json
import re
from pathlib import Path

import httpx
import pymupdf
import pytest

from papertrans.translation import create_translation_provider
from papertrans.translation_job import run_translation_job


def create_provider_pdf_fixture(path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=420, height=595)
    page.insert_text(
        (40, 55),
        "Provider Translation Test",
        fontsize=16,
        fontname="tibo",
    )
    page.insert_textbox(
        pymupdf.Rect(40, 85, 190, 330),
        "This paper paragraph cites [1] and https://example.org/model. "
        "The measured latency is 10 ms and the method preserves layout.",
        fontsize=9,
        fontname="tiro",
    )
    page.insert_textbox(
        pymupdf.Rect(230, 85, 380, 330),
        "A second column verifies reading order, compact translation, and page geometry.",
        fontsize=9,
        fontname="tiro",
    )
    document.save(path)
    document.close()
    return path


@pytest.mark.parametrize(
    ("provider_name", "key_env", "usage", "currency", "expected_cost"),
    [
        (
            "deepseek",
            "DEEPSEEK_API_KEY",
            {
                "prompt_tokens": 100,
                "prompt_cache_hit_tokens": 20,
                "prompt_cache_miss_tokens": 80,
                "completion_tokens": 30,
                "total_tokens": 130,
            },
            "USD",
            0.000019656,
        ),
        (
            "kimi",
            "MOONSHOT_API_KEY",
            {
                "prompt_tokens": 100,
                "cached_tokens": 20,
                "completion_tokens": 30,
                "total_tokens": 130,
            },
            "CNY",
            0.001352,
        ),
    ],
)
def test_named_provider_pipeline_preserves_pdf_and_never_persists_key(
    tmp_path: Path,
    provider_name: str,
    key_env: str,
    usage: dict[str, int],
    currency: str,
    expected_cost: float,
) -> None:
    sentinel = f"sk-{provider_name}-sentinel-never-write"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        body = json.loads(request.content)
        user_payload = json.loads(body["messages"][1]["content"])
        tokens = "".join(user_payload["protected_tokens"])
        content = json.dumps(
            {
                "normal": f"这是完整的论文中文译文{tokens}",
                "compact": f"这是紧凑论文译文{tokens}",
            },
            ensure_ascii=False,
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": content}, "finish_reason": "stop"}
                ],
                "usage": usage,
            },
        )

    source = create_provider_pdf_fixture(tmp_path / "source.pdf")
    cache_dir = tmp_path / "cache"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first_provider = create_translation_provider(
            provider_name,
            environ={key_env: sentinel},
            http_client=client,
        )
        first = run_translation_job(
            source,
            tmp_path / "first",
            first_provider,
            cache_dir=cache_dir,
        )

        first_call_count = calls
        second_provider = create_translation_provider(
            provider_name,
            environ={key_env: sentinel},
            http_client=client,
        )
        second = run_translation_job(
            source,
            tmp_path / "second",
            second_provider,
            cache_dir=cache_dir,
        )

    assert first.report["passed"] is True
    assert first.report["protection"]["passed"] is True
    assert first.report["layout"]["translated_line_overlap_count"] == 0
    assert first.report["layout"]["protected_region_overlap_count"] == 0
    assert first_call_count > 0
    protection_manifest = json.loads(
        first.protected_segments_json.read_text(encoding="utf-8")
    )
    protected_values = {
        token["value"]: token["kind"]
        for segment in protection_manifest["segments"]
        for token in segment["tokens"]
    }
    assert protected_values["[1]"] == "citation"
    assert protected_values["https://example.org/model"] == "url"
    assert protected_values["10 ms"] == "unit"
    assert all(item["passed"] for item in protection_manifest["validations"])
    with pymupdf.open(first.output_pdf) as translated_pdf:
        rendered_text = "".join(page.get_text() for page in translated_pdf)
    compact_rendered_text = re.sub(r"\s+", "", rendered_text)
    for value in ("[1]", "https://example.org/model", "10ms"):
        assert value in compact_rendered_text

    first_usage = first.report["provider_execution"]["usage"]
    assert first_usage == {
        "input_tokens": 100 * first_call_count,
        "cached_input_tokens": 20 * first_call_count,
        "uncached_input_tokens": 80 * first_call_count,
        "output_tokens": 30 * first_call_count,
        "estimated_cost": pytest.approx(expected_cost * first_call_count),
        "currency": currency,
        "pricing_snapshot": "2026-07-31",
    }

    assert calls == first_call_count
    assert second.report["passed"] is True
    assert second.report["provider_execution"]["cache_hits"] == first_call_count
    assert second.report["provider_execution"]["provider_calls"] == 0
    assert second.report["provider_execution"]["usage"] == {
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "uncached_input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": None,
        "currency": None,
        "pricing_snapshot": None,
    }

    searchable = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for root in (tmp_path / "first", tmp_path / "second", cache_dir)
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".json", ".md", ".txt"}
    )
    assert sentinel not in searchable
