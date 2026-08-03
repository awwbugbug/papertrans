from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = PROJECT_ROOT / "frontend" / "src-tauri"


def test_tauri_window_configuration_preserves_native_window_behavior() -> None:
    config = json.loads((TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8"))
    window = config["app"]["windows"][0]

    assert window["decorations"] is False
    assert window["resizable"] is True
    assert window["shadow"] is True


def test_tauri_capability_allows_custom_titlebar_commands() -> None:
    capability = json.loads(
        (TAURI_ROOT / "capabilities" / "default.json").read_text(encoding="utf-8")
    )
    permissions = set(capability["permissions"])

    assert {
        "core:window:allow-close",
        "core:window:allow-minimize",
        "core:window:allow-start-dragging",
        "core:window:allow-toggle-maximize",
    } <= permissions
