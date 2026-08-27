from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class DesktopStorageManager:
    """Own bounded maintenance for PaperTrans-managed cache and upload copies."""

    def __init__(self, data_root: str | Path, uploads_root: str | Path) -> None:
        self.data_root = Path(data_root).expanduser().resolve()
        self.cache_root = (self.data_root / "cache").resolve()
        self.uploads_root = Path(uploads_root).expanduser().resolve()
        if self.cache_root.parent != self.data_root:
            raise ValueError("Invalid desktop cache root")
        if not _is_within(self.uploads_root, self.data_root) or self.uploads_root == self.data_root:
            raise ValueError("Invalid desktop upload root")
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.uploads_root.mkdir(parents=True, exist_ok=True)

    def snapshot(self) -> dict[str, Any]:
        return {
            "cache": _directory_usage(self.cache_root),
            "temporaryUploads": _directory_usage(self.uploads_root),
        }

    def clear_cache(self) -> dict[str, Any]:
        removed = _directory_usage(self.cache_root)
        _clear_children(self.cache_root)
        return {"cleared": True, "removed": removed, "storage": self.snapshot()}

    def clear_orphan_uploads(self, retained_paths: Iterable[str | Path]) -> dict[str, Any]:
        retained = {Path(path).expanduser().resolve() for path in retained_paths}
        removed_files = 0
        removed_bytes = 0
        for child in list(self.uploads_root.iterdir()):
            child_resolved = child.resolve()
            if any(_is_within(path, child_resolved) for path in retained):
                continue
            usage = _entry_usage(child)
            _remove_managed_entry(child, self.uploads_root)
            removed_files += int(usage["fileCount"])
            removed_bytes += int(usage["bytes"])
        return {
            "cleared": True,
            "removed": {"fileCount": removed_files, "bytes": removed_bytes},
            "storage": self.snapshot(),
        }


def remove_managed_entry(path: Path, root: Path) -> None:
    _remove_managed_entry(path, root)


def _directory_usage(root: Path) -> dict[str, int]:
    if not root.is_dir():
        return {"fileCount": 0, "bytes": 0}
    files = 0
    total_bytes = 0
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode):
                    files += 1
                    total_bytes += max(0, int(info.st_size))
                elif stat.S_ISDIR(info.st_mode) and not _is_reparse_point(info):
                    stack.append(Path(entry.path))
    return {"fileCount": files, "bytes": total_bytes}


def _entry_usage(path: Path) -> dict[str, int]:
    try:
        info = path.lstat()
    except OSError:
        return {"fileCount": 0, "bytes": 0}
    if _is_reparse_point(info) or path.is_symlink():
        return {"fileCount": 0, "bytes": 0}
    if stat.S_ISDIR(info.st_mode):
        return _directory_usage(path)
    return {
        "fileCount": 1 if stat.S_ISREG(info.st_mode) else 0,
        "bytes": max(0, int(info.st_size)) if stat.S_ISREG(info.st_mode) else 0,
    }


def _clear_children(root: Path) -> None:
    resolved = root.resolve()
    for child in list(resolved.iterdir()):
        _remove_managed_entry(child, resolved)


def _remove_managed_entry(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    lexical_path = Path(os.path.abspath(path))
    if lexical_path.parent != resolved_root and not _is_within(lexical_path.parent, resolved_root):
        raise ValueError("Refusing to remove a path outside the managed root")
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if path.is_symlink() or _is_reparse_point(info):
        if stat.S_ISDIR(info.st_mode):
            os.rmdir(path)
        else:
            path.unlink()
    elif stat.S_ISDIR(info.st_mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def _is_reparse_point(info: os.stat_result) -> bool:
    attributes = int(getattr(info, "st_file_attributes", 0))
    flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
    return bool(flag and attributes & flag)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
