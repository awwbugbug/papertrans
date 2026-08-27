import json
from pathlib import Path

import pymupdf

from papertrans.desktop.library import LIBRARY_SCHEMA, LocalTaskLibrary


def test_text_task_survives_restart_without_body_in_index(tmp_path: Path) -> None:
    root = tmp_path / "library"
    source = "A private paragraph with [7]."
    translation = "包含 [7] 的私有段落。"
    task = LocalTaskLibrary(root).add_text_task(
        source_text=source,
        translation=translation,
        provider="mock",
    )

    restarted = LocalTaskLibrary(root)
    listing = restarted.list_tasks()
    detail = restarted.get_task(task["id"])
    index_text = (root / "library.json").read_text(encoding="utf-8")

    assert listing == [task]
    assert task["title"] == "文本翻译"
    assert task["preview"] == source
    assert detail["sourceText"] == source
    assert detail["translation"] == translation
    assert source not in index_text
    assert translation not in index_text
    assert json.loads(index_text)["schema"] == LIBRARY_SCHEMA


def test_text_task_listing_returns_only_a_bounded_normalized_preview(tmp_path: Path) -> None:
    source = "  Uniﬁed title.\n\n" + "A" * 180
    library = LocalTaskLibrary(tmp_path / "library")
    task = library.add_text_task(
        source_text=source,
        translation="译文",
        provider="mock",
    )

    restarted_task = LocalTaskLibrary(tmp_path / "library").list_tasks()[0]

    assert restarted_task["preview"] == task["preview"]
    assert restarted_task["preview"].startswith("Unified title. ")
    assert restarted_task["preview"].endswith("…")
    assert len(restarted_task["preview"]) == 120
    assert "A" * 121 not in (tmp_path / "library" / "library.json").read_text(
        encoding="utf-8"
    )


def test_pdf_task_status_and_paths_survive_restart(tmp_path: Path) -> None:
    root = tmp_path / "library"
    source = (tmp_path / "paper.pdf").resolve()
    output_dir = (tmp_path / "out").resolve()
    output_pdf = output_dir / "output.pdf"
    library = LocalTaskLibrary(root)
    library.create_pdf_task(
        task_id="a" * 32,
        source_path=source,
        output_dir=output_dir,
        provider="mock",
        created_at="2026-08-25T00:00:00+00:00",
    )
    library.update_pdf_task(
        "a" * 32,
        status="completed",
        message="翻译完成",
        output_dir=output_dir,
        output_pdf=output_pdf,
    )

    detail = LocalTaskLibrary(root).get_task("a" * 32)

    assert detail["status"] == "completed"
    assert detail["sourcePath"] == str(source)
    assert detail["outputPdf"] == str(output_pdf)
    assert LocalTaskLibrary(root).open_path("a" * 32) == output_dir


def test_pdf_task_uses_first_page_paper_title_instead_of_filename(tmp_path: Path) -> None:
    source = tmp_path / "1504.08083v2.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 90), "Fast R-CNN", fontsize=24)
    page.insert_text((72, 150), "This paper presents an object detection method.", fontsize=10)
    document.save(source)
    document.close()

    task = LocalTaskLibrary(tmp_path / "library").create_pdf_task(
        task_id="b" * 32,
        source_path=source,
        output_dir=tmp_path / "output",
        provider="mock",
        created_at="2026-08-25T00:00:00+00:00",
    )

    assert task["title"] == "Fast R-CNN"


def test_old_pdf_filename_title_is_backfilled_once(tmp_path: Path) -> None:
    source = tmp_path / "paper.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 90), "A Stable Academic Paper Title", fontsize=22)
    page.insert_text((72, 150), "Body copy for font-size comparison.", fontsize=10)
    document.save(source)
    document.close()
    root = tmp_path / "library"
    root.mkdir()
    (root / "library.json").write_text(
        json.dumps(
            {
                "schema": LIBRARY_SCHEMA,
                "tasks": [
                    {
                        "id": "c" * 32,
                        "kind": "pdf",
                        "title": source.name,
                        "provider": "mock",
                        "status": "completed",
                        "message": "翻译完成",
                        "createdAt": "2026-08-25T00:00:00+00:00",
                        "updatedAt": "2026-08-25T00:00:00+00:00",
                        "sourcePath": str(source),
                        "outputDir": str(tmp_path / "output"),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    task = LocalTaskLibrary(root).list_tasks()[0]
    persisted = json.loads((root / "library.json").read_text(encoding="utf-8"))["tasks"][0]

    assert task["title"] == "A Stable Academic Paper Title"
    assert persisted["title"] == task["title"]
    assert persisted["libraryTitleResolved"] is True


def test_text_task_deletion_removes_internal_files_and_index_record(tmp_path: Path) -> None:
    root = tmp_path / "library"
    library = LocalTaskLibrary(root)
    task = library.add_text_task(
        source_text="Private source text",
        translation="私有译文",
        provider="mock",
    )

    deleted = library.delete_task(task["id"])

    assert deleted == {
        "id": task["id"],
        "kind": "text",
        "internalFilesRemoved": True,
    }
    assert not (root / task["id"]).exists()
    assert library.list_tasks() == []
    assert json.loads((root / "library.json").read_text(encoding="utf-8"))["tasks"] == []
