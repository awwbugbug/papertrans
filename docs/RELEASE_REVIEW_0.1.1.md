# PaperTrans 0.1.1 release review

Date: 2026-08-26

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
