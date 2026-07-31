import json
from pathlib import Path

import pytest

from papertrans.domain import Document, RegionType, TextFlow
from papertrans.translation.context import build_translation_contexts, load_glossary


def _flow(flow_id: str, flow_type: RegionType, text: str) -> TextFlow:
    return TextFlow(
        id=flow_id,
        type=flow_type,
        region_ids=[f"region-{flow_id}"],
        page_numbers=[1],
        raw_text=text,
        source_text=text,
        translatable=True,
    )


def test_context_uses_active_heading_immediate_neighbors_and_relevant_glossary() -> None:
    document = Document(
        source_path="fixture.pdf",
        text_flows=[
            _flow("heading", RegionType.HEADING, "3. Region Proposal Networks"),
            _flow("first", RegionType.PARAGRAPH, "The region proposal module shares features."),
            _flow("current", RegionType.PARAGRAPH, "A region proposal is scored by IoU."),
            _flow("next", RegionType.PARAGRAPH, "The detector consumes each proposal."),
        ],
    )

    contexts, stats = build_translation_contexts(
        document,
        glossary={"region proposal": "候选区域", "unrelated term": "无关术语"},
    )

    assert contexts["current"] == {
        "schema_version": "m5c_v1",
        "region_type": "paragraph",
        "section_title": "3. Region Proposal Networks",
        "previous_text": "The region proposal module shares features.",
        "next_text": "The detector consumes each proposal.",
        "glossary": [{"source": "region proposal", "target": "候选区域"}],
    }
    assert stats.flow_count == 4
    assert stats.section_title_count == 4
    assert stats.glossary_term_count == 2


def test_context_is_bounded_and_never_includes_distant_paragraphs() -> None:
    previous = f"previous {'a' * 800}"
    following = f"following {'b' * 800}"
    distant = "DISTANT-SENTINEL"
    document = Document(
        source_path="fixture.pdf",
        text_flows=[
            _flow("previous", RegionType.PARAGRAPH, previous),
            _flow("current", RegionType.PARAGRAPH, "current"),
            _flow("following", RegionType.PARAGRAPH, following),
            _flow("distant", RegionType.PARAGRAPH, distant),
        ],
    )

    contexts, stats = build_translation_contexts(document)
    current = contexts["current"]

    assert len(current["previous_text"]) <= 600
    assert len(current["next_text"]) <= 600
    assert distant not in json.dumps(current)
    assert stats.clipped_neighbor_count == 2


def test_load_glossary_accepts_json_object_and_rejects_invalid_content(
    tmp_path: Path,
) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps({"region proposal": "候选区域"}, ensure_ascii=False),
        encoding="utf-8",
    )
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    assert load_glossary(valid) == {"region proposal": "候选区域"}
    with pytest.raises(ValueError, match="Invalid glossary file"):
        load_glossary(invalid)


def test_load_glossary_errors_do_not_echo_term_content(tmp_path: Path) -> None:
    sentinel = "secret-paper-term"
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({sentinel: ""}), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        load_glossary(invalid)

    assert str(exc_info.value) == "Invalid glossary file"
    assert sentinel not in str(exc_info.value)


def test_context_builder_validates_library_supplied_glossary() -> None:
    document = Document(
        source_path="fixture.pdf",
        text_flows=[_flow("flow", RegionType.PARAGRAPH, "source")],
    )

    with pytest.raises(ValueError, match="Invalid glossary file"):
        build_translation_contexts(document, glossary={"source": ""})
