# PaperTrans 0.1.1 release review

Date: 2026-08-26

## 2026-08-27 pre-publication recheck

The original review below is historical. The licensing decision was completed on 2026-08-27 and
the public binary release is now published at:
https://github.com/awwbugbug/papertrans/releases/tag/v0.1.1

### Distribution licensing

`pyproject.toml` and README declare Apache-2.0, but the repository contains no root LICENSE file.
The installed and bundled PyMuPDF 1.28.0 metadata declares AGPL-3.0 or an Artifex commercial license,
consistent with the [upstream licensing documentation](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright).
The project declaration does not replace dependency licenses. The release follows the AGPL-3.0
route, with the required third-party notices and corresponding-source arrangement documented in
`THIRD_PARTY_NOTICES.md`.

### Frozen OCR regression found before publication

The installer includes both PP-OCRv6 model directories, and their files match the local originals.
However, an actual synthetic scanned-page job failed even though `/api/system` reported OCR ready.
The same input succeeded from the source environment. A diagnostic-only copy of the frozen backend
showed two packaging omissions:

- PaddleX package data, including `configs/pipelines/OCR.yaml`, was missing.
- Distribution metadata for `imagesize`, `opencv-contrib-python`, `pyclipper`, `pypdfium2`,
  `python-bidi`, and `shapely` was missing, so PaddleX rejected its `ocr-core` dependency check.

Adding only those resources to the diagnostic copy enabled real recognition of six lines from the
synthetic scan. The release script now collects the same resources without modifying OCR algorithms
or bypassing dependency validation. `tests/test_release_sidecar.py` reproduces the original failure
against the actual executable and is now a mandatory build gate, including with `-SkipTests`.
It exercises authenticated startup, real local OCR, Mock translation, PDF quality checks, and output
retrieval in an isolated test directory, with no user documents or paid provider calls.

The rebuilt frozen sidecar passed this complete regression in 32.23 seconds. The test tolerates
transient read-connection failures during cold model initialization only within its fixed 180-second
job deadline, checks that the process remains alive, and still requires successful OCR, translation,
quality validation, and PDF retrieval. It never resubmits the translation request. The same gate
also passed in 38.78 seconds against the backend and models extracted from the final NSIS installer.

### Final local artifact verification

- Build source: `33a5915` (subsequent review updates are documentation-only).
- Installer: `PaperTrans_0.1.1_x64-setup.exe`, 368,537,231 bytes (351.5 MiB).
- Installer SHA256: `7301718DB3D208B859EA391B5F5B5A74A12A9DB81080A94A4DE7E7435BB3FB8F`.
- `SHA256SUMS.txt` matches the final installer.
- NSIS archive extraction succeeded. All six model files match the source files by SHA256.
- Extracted backend matches the tested build byte-for-byte; SHA256:
  `9A18C06CBB17612086F64B85F848BD9E94636D2E0A5B3FF26C66262DA3C1CD0F`.
- Extracted desktop executable matches the build except for Tauri's documented-in-source
  `__TAURI_BUNDLE_TYPE_VAR_UNK` to `__TAURI_BUNDLE_TYPE_VAR_NSS` bundle marker. Both executables
  use the Windows GUI subsystem.
- Authenticode status remains `NotSigned`.
- Remote README, screenshots, packaging script, and regression test match local Git blobs;
  both screenshot URLs returned HTTP 200.

These checks exercise the extracted installed resources, not an interactive installation on a
separate clean Windows machine. The verified installer and checksum file are now attached to the
public v0.1.1 release.

### Source and documentation checks

- Both README screenshots were present locally but referenced under nonexistent filenames; the
  references now match the actual images, with no unmasked API key visible in either screenshot.
- README now documents output-directory preferences, dark theme, bundled-versus-development OCR,
  checksums, unsigned-installer warnings, current limitations, and the AGPL third-party notices.
- Python: 252 passed, one opt-in frozen-sidecar test skipped in the ordinary source-only run.
- UI contracts: 40 passed. Sites compatibility: 4 passed. TypeScript and Vite build: passed.
- Ruff, Rust release check, and Clippy with warnings denied: passed.
- Production frontend dependency audit: no known vulnerabilities reported.
- Tracked-file scan: no common secret-pattern matches, model weights, development caches, test PDFs,
  or installer binaries. This is a bounded scan, not a guarantee that every possible secret is absent.

## Scope

This review covers the Windows Tauri shell, packaged Python sidecar, NSIS output, dependency
classification, local API security boundary, and the existing automated regression suite. It does
not repeat the already accepted PDF layout-quality evaluation.

## Fixed findings

### P1 — Windows executable used the console subsystem

The release entry point did not declare the Windows GUI subsystem. PE inspection therefore showed
`Windows CUI`, which created a terminal window when the installed app started. The release-only
`windows_subsystem = "windows"` attribute is now present; the final executable reports
`Windows GUI`. Debug builds keep their console diagnostics.

### P1 — icon files were generated but not wired into the bundle

`bundle.icon` was absent and NSIS did not define `installerIcon`, so incremental compilation kept
the old embedded application icon and NSIS used its default installer icon. The app icon set and
the installer/uninstaller icon are now explicit in `tauri.conf.json`. Icons extracted from both
final 0.1.1 executables match the selected PaperTrans artwork.

### P1 — packaged sidecar could survive an abnormal desktop exit

The PyInstaller one-file sidecar uses a parent/child process pair. Killing only the shell plugin's
outer child handle could leave the inner service alive after a crash or forced replacement. The
sidecar is now assigned immediately to a Windows Job Object with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so closing the desktop process handle terminates the complete
sidecar tree. Normal tray hiding intentionally keeps the job handle and backend alive.

### P1 — multiple desktop instances could share one data directory

The desktop shell had no single-instance guard. The official Tauri single-instance plugin is now
registered before all other plugins. A second launch exits and restores/focuses the existing main
window instead of starting another backend.

### P1 — known Vite 6.4.2 development-server vulnerabilities

The frontend build tools were incorrectly classified as runtime dependencies and Vite 6.4.2 was
affected by the Windows path advisories reported by `pnpm audit`. Build-only packages now live in
`devDependencies`, Vite is 6.4.3, and the production dependency audit reports no known
vulnerabilities.

## Positive findings

- The Python service binds only to a random `127.0.0.1` port and every API request requires a
  per-session token.
- Provider secrets remain in Windows Credential Manager and were not found in tracked source.
- Tauri capabilities expose only the window and dialog permissions required by the current UI.
- The packaged Python sidecar is already a `Windows GUI` binary and suppresses Uvicorn console
  logging correctly.
- Library deletion and cache cleanup stay within validated application-managed roots.
- PDF rendering remains bounded to a small virtual page window rather than retaining every page at
  high resolution.

## Remaining release risks

### P2 — installer is unsigned

The NSIS installer has no Authenticode signature. Windows SmartScreen can therefore show an
unknown-publisher warning. Public distribution should add a code-signing certificate and sign both
the application executable and installer.

### P2 — Tauri CSP is currently disabled

`app.security.csp` remains `null`. The application uses bundled assets and a token-protected
loopback API, which limits present exposure, but a restrictive tested CSP should be added before a
broad public release. This needs dedicated PDF.js/WebView validation because an incorrect policy
can break workers, fonts, blob URLs, or the local API connection.

### P3 — installer size

The installer is about 253.5 MiB because the offline OCR/Paddle runtime is bundled. A future
optional OCR component or separate lightweight installer could reduce download size without
changing translation behavior.

## Verification

- Final application PE subsystem: `Windows GUI`.
- Application and installer icons extracted from the final binaries: passed visual inspection.
- Python suite: 230 tests passed.
- UI contract suite: 28 tests passed.
- Sites compatibility suite: 4 tests passed.
- Ruff: passed.
- Rust release check and Clippy with warnings denied: passed.
- Production dependency audit: no known vulnerabilities.
- Tracked secret-pattern scan: zero matching files.
