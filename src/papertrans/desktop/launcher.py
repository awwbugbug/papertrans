from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _windows_vsdevcmd() -> Path:
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    vswhere = program_files_x86 / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if vswhere.is_file():
        result = subprocess.run(
            [
                str(vswhere),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            candidate = Path(result.stdout.strip()) / "Common7" / "Tools" / "VsDevCmd.bat"
            if candidate.is_file():
                return candidate

    editions = ("BuildTools", "Community", "Professional", "Enterprise")
    for edition in editions:
        candidate = (
            program_files_x86
            / "Microsoft Visual Studio"
            / "2022"
            / edition
            / "Common7"
            / "Tools"
            / "VsDevCmd.bat"
        )
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "Visual Studio C++ Build Tools were not found. Install the Desktop development with C++ "
        "workload before starting PaperTrans."
    )


def main() -> None:
    repository = Path(__file__).resolve().parents[3]
    frontend = repository / "frontend"
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        raise RuntimeError("pnpm is required to start the PaperTrans Tauri desktop client")
    if os.name == "nt":
        vsdevcmd = _windows_vsdevcmd()
        cargo_bin = Path(os.environ.get("USERPROFILE", str(Path.home()))) / ".cargo" / "bin"
        command = (
            f'call "{vsdevcmd}" -arch=amd64 -host_arch=amd64 >nul '
            f'&& set "PATH={cargo_bin};%PATH%" '
            f'&& call "{pnpm}" desktop:dev'
        )
        arguments = ["cmd.exe", "/d", "/s", "/c", command]
    else:
        arguments = [pnpm, "desktop:dev"]
    completed = subprocess.run(arguments, cwd=frontend, check=False)
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
