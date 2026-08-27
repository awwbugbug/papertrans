from pathlib import Path

import pytest

from papertrans.desktop.storage import DesktopStorageManager


def test_cache_cleanup_is_bounded_to_the_managed_cache_root(tmp_path: Path) -> None:
    data_root = tmp_path / ".papertrans"
    uploads_root = data_root / "jobs" / "uploads"
    storage = DesktopStorageManager(data_root, uploads_root)
    cache_file = data_root / "cache" / "deepseek" / "aa" / "entry.json"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"cached-result")
    outside = tmp_path / "user-paper.pdf"
    outside.write_bytes(b"original")

    before = storage.snapshot()
    result = storage.clear_cache()

    assert before["cache"] == {"fileCount": 1, "bytes": len(b"cached-result")}
    assert result["removed"] == before["cache"]
    assert result["storage"]["cache"] == {"fileCount": 0, "bytes": 0}
    assert (data_root / "cache").is_dir()
    assert outside.read_bytes() == b"original"


def test_upload_cleanup_preserves_referenced_copies_only(tmp_path: Path) -> None:
    data_root = tmp_path / ".papertrans"
    uploads_root = data_root / "jobs" / "uploads"
    storage = DesktopStorageManager(data_root, uploads_root)
    retained = uploads_root / "retained" / "paper.pdf"
    orphan = uploads_root / "orphan" / "paper.pdf"
    retained.parent.mkdir(parents=True)
    orphan.parent.mkdir(parents=True)
    retained.write_bytes(b"keep")
    orphan.write_bytes(b"remove")

    result = storage.clear_orphan_uploads({retained})

    assert retained.read_bytes() == b"keep"
    assert not orphan.parent.exists()
    assert result["removed"] == {"fileCount": 1, "bytes": len(b"remove")}


def test_storage_rejects_an_upload_root_outside_its_data_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="upload root"):
        DesktopStorageManager(tmp_path / ".papertrans", tmp_path / "outside-uploads")
