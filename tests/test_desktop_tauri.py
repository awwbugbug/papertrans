from __future__ import annotations

import json
from pathlib import Path

from papertrans.desktop import launcher

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = PROJECT_ROOT / "frontend" / "src-tauri"


def test_tauri_window_configuration_preserves_native_window_behavior() -> None:
    config = json.loads((TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8"))
    window = config["app"]["windows"][0]

    assert window["decorations"] is False
    assert window["resizable"] is True
    assert window["shadow"] is True


def test_tauri_frontend_hooks_do_not_require_a_global_pnpm_command() -> None:
    config = json.loads((TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8"))
    build = config["build"]

    assert build["beforeDevCommand"] == "corepack pnpm dev --port 1420"
    assert build["beforeBuildCommand"] == "corepack pnpm build"


def test_tauri_bundle_uses_the_papertrans_icon_for_app_and_nsis() -> None:
    config = json.loads((TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8"))
    bundle = config["bundle"]

    assert "icons/icon.ico" in bundle["icon"]
    assert "icons/32x32.png" in bundle["icon"]
    assert bundle["windows"]["nsis"]["installerIcon"] == "icons/icon.ico"
    assert bundle["windows"]["nsis"]["uninstallerIcon"] == "icons/icon.ico"


def test_release_bundle_includes_and_routes_the_local_ocr_models() -> None:
    config = json.loads((TAURI_ROOT / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = config["bundle"]["resources"]
    rust = (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")
    release_script = (PROJECT_ROOT / "scripts" / "build_windows_release.ps1").read_text(
        encoding="utf-8"
    )

    assert resources[
        "../../models/paddleocr/PP-OCRv6_medium_det_infer"
    ] == "models/paddleocr/PP-OCRv6_medium_det_infer"
    assert resources[
        "../../models/paddleocr/PP-OCRv6_medium_rec_infer"
    ] == "models/paddleocr/PP-OCRv6_medium_rec_infer"
    assert '.join("models")' in rust
    assert '.join("paddleocr")' in rust
    assert '"--ocr-model-dir"' in rust
    assert "inference.pdiparams" in release_script


def test_tauri_build_recompiles_the_windows_executable_when_the_icon_changes() -> None:
    build_script = (TAURI_ROOT / "build.rs").read_text(encoding="utf-8")

    assert 'cargo:rerun-if-changed=icons/icon.ico' in build_script


def test_release_binary_uses_the_windows_gui_subsystem() -> None:
    main_source = (TAURI_ROOT / "src" / "main.rs").read_text(encoding="utf-8")

    assert '#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]' in main_source


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


def test_tauri_persists_provider_configuration_in_native_credentials() -> None:
    cargo = (TAURI_ROOT / "Cargo.toml").read_text(encoding="utf-8")
    rust = (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")

    assert 'keyring = "4.1"' in cargo
    assert 'serde_json = "1"' in cargo
    assert "load_provider_configs" in rust
    assert "save_provider_config" in rust
    assert "keyring::v1::{Entry" in rust
    assert "PaperTrans/provider-config" in rust
    assert "deepseek" in rust and "kimi" in rust and "compatible" in rust
    assert "println!" not in rust


def test_tauri_close_behavior_uses_a_restorable_system_tray() -> None:
    cargo = (TAURI_ROOT / "Cargo.toml").read_text(encoding="utf-8")
    rust = (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")

    assert 'tauri = { version = "2", features = ["tray-icon"] }' in cargo
    assert "TrayIconBuilder" in rust
    assert "WindowEvent::CloseRequested" in rust
    assert "api.prevent_close()" in rust
    assert "window.hide()" in rust
    assert "set_exit_on_close" in rust
    assert "show_main_window" in rust
    assert '"tray-quit"' in rust


def test_packaged_sidecar_is_bound_to_a_windows_kill_on_close_job() -> None:
    cargo = (TAURI_ROOT / "Cargo.toml").read_text(encoding="utf-8")
    rust = (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")

    assert 'windows-sys = { version = "0.61"' in cargo
    assert "JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE" in rust
    assert "AssignProcessToJobObject" in rust
    assert "attach_backend_job" in rust


def test_desktop_is_single_instance_and_restores_the_existing_window() -> None:
    cargo = (TAURI_ROOT / "Cargo.toml").read_text(encoding="utf-8")
    rust = (TAURI_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")

    assert 'tauri-plugin-single-instance = "2"' in cargo
    single_instance = ".plugin(tauri_plugin_single_instance::init"
    assert single_instance in rust
    assert rust.index(single_instance) < rust.index(".plugin(tauri_plugin_dialog::init())")
    assert "show_main_window(app)" in rust


def test_windows_launcher_passes_cmd_command_line_without_list_escaping(
    monkeypatch,
    tmp_path: Path,
) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    vsdevcmd = Path(
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
        r"\Common7\Tools\VsDevCmd.bat"
    )
    msvc_linker = Path(
        r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"
        r"\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\link.exe"
    )
    calls: list[tuple[object, Path]] = []

    class Completed:
        returncode = 0

    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(
        launcher,
        "__file__",
        str(tmp_path / "src" / "papertrans" / "desktop" / "launcher.py"),
    )
    monkeypatch.setattr(launcher, "_windows_vsdevcmd", lambda: vsdevcmd)
    monkeypatch.setattr(launcher, "_windows_msvc_linker", lambda path: msvc_linker)
    monkeypatch.setattr(launcher.shutil, "which", lambda name: r"C:\pnpm\pnpm.cmd")
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda arguments, cwd, check: calls.append((arguments, cwd)) or Completed(),
    )

    try:
        launcher.main()
    except SystemExit as error:
        assert error.code == 0

    arguments, cwd = calls[0]
    assert isinstance(arguments, str)
    assert arguments.startswith("cmd.exe /d /s /c ")
    assert f"CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER={msvc_linker}" in arguments
    assert '\\"' not in arguments
    assert cwd == frontend


def test_windows_launcher_resolves_the_x64_msvc_linker(tmp_path: Path) -> None:
    vs_root = tmp_path / "Microsoft Visual Studio" / "2022" / "BuildTools"
    vsdevcmd = vs_root / "Common7" / "Tools" / "VsDevCmd.bat"
    older = vs_root / "VC" / "Tools" / "MSVC" / "14.40.00000" / "bin" / "Hostx64" / "x64"
    newer = vs_root / "VC" / "Tools" / "MSVC" / "14.44.35207" / "bin" / "Hostx64" / "x64"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "link.exe").touch()
    (newer / "link.exe").touch()

    assert launcher._windows_msvc_linker(vsdevcmd) == newer / "link.exe"
