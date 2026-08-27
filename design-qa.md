# PaperTrans Academic Precision Restyle — Design QA

## Scope

- Visual source: `frontend_tamplate/stitch_papertrans_ui_1/screen.png`
- Implementation: the existing React/Tauri translation workspace
- Constraint: preserve the five functional modules, splitters, collapsed bars, navigation, native
  window controls, and current desktop behavior.
- Final implementation capture: `artifacts/design-qa/implementation-academic-precision-final.png`
- Side-by-side comparison: `artifacts/design-qa/comparison-academic-precision-final.png`

## Capture normalization

- Reference bitmap: 1600 x 1280.
- Implementation viewport and capture: 1600 x 1065 CSS pixels at device scale factor 1.
- For direct visual comparison, the reference's top 1600 x 1065 region was paired with the
  implementation capture without scaling. The lower 215 pixels of the taller reference are
  intentionally outside the comparison.
- State: empty translation workspace, Translate navigation active, settings expanded.

## Visual findings

- The former Apple-like translucent surfaces and large radii are removed.
- The implementation now follows the reference's neutral paper/grey surfaces, deep indigo accent,
  one-pixel outlines, compact density, restrained 4-8 px radii, and minimal shadow.
- Inter remains the primary UI typeface; Geist is used for compact labels and JetBrains Mono for
  terse metadata. Material Symbols provides the shared icon language.
- Header hierarchy, active navigation treatment, upload target, section bars, settings controls,
  empty states, and status accents visually match the source language.
- The five-module arrangement intentionally differs from the two-pane reference because the user
  explicitly required the existing functionality and layout to remain unchanged.
- Native Windows controls intentionally replace the reference's export action in the title bar.

## Comparison history

- P2: the settings area initially lacked the reference's explicit section heading and bilingual
  metadata line. Fixed by adding the compact `翻译设置 / Translation Settings` header.
- P3: upload and empty-state icons initially inherited a smaller generic icon size. Fixed with
  scoped sizes that preserve hierarchy without enlarging unrelated controls.
- No remaining P0, P1, or P2 visual defects were found in the final comparison.

## Interaction and regression checks

- Navigation between Translate and Settings works without changing shell geometry.
- Provider menu opens with the expected custom low-radius listbox.
- Text entry updates the live character count.
- Keyboard-accessible splitters resize and collapse/restore text, PDF, and settings surfaces.
- Browser console checked with no errors or warnings in the verified state.
- TypeScript typecheck passed.
- Production frontend build passed.
- Sites worker compatibility suite passed: 4 tests.
- Python regression suite passed: 197 tests, with one upstream Starlette deprecation warning.
- Ruff passed with no findings.

## Final Result

passed

## Global application icon — 2026-08-26

- Source truth: `assets/branding/papertrans-icon-reference.png` (1254 x 1254 RGBA).
- Implementation master: `assets/branding/papertrans-icon.png` (1024 x 1024 RGBA), with an
  editable traced companion at `assets/branding/papertrans-icon.svg`.
- Full-view comparison: `build/branding-qa-comparison.png` at 2048 x 1024, device density 1. The
  source and exported master are shown on the same neutral background with no browser or viewport
  scaling involved.
- Focused small-size evidence: `frontend/src-tauri/icons/32x32.png` remains recognizable and keeps
  the two-page silhouette, paper surfaces, indigo connector, and internal text marks distinct.
- The first traced implementation exposed isolated seam speckles at extreme magnification. The
  Windows icon pipeline now exports from the normalized PNG master, preserving the accepted
  gradients and antialiasing without propagating vector-trace artifacts.
- Tauri regenerated the complete ICO/PNG/ICNS platform set. The Windows ICO contains 16, 24, 32,
  48, 64, and 256 px frames, so the window, taskbar, tray, desktop shortcut, and installer share the
  same artwork.
- No remaining P0, P1, or P2 visual defects were found.

## Final Result

passed

## Motion refinement — 2026-08-25

- Navigation uses one shared selection surface with a 220 ms
  `cubic-bezier(.22, 1, .36, 1)` translation.
- Library, Translate, and Settings pages enter directionally over 240 ms with the same curve.
- Workspace panel expansion remains immediate; the initial 260 ms clipped reveal was removed after
  user review because it weakened the interaction feel.
- The active navigation surface is exactly 40 px high with the same 4 px radius as the hover box.
- The library action uses the Material Symbols 22 px plus codepoint in a fixed 20 px slot so it
  cannot flash the icon's ligature name, with balanced padding and a 7 px icon-to-label gap.
- `prefers-reduced-motion` reduces navigation and page motion to 1 ms.
- Browser interaction checks verified forward/backward navigation and final component geometry.

## Header density and text selection refinement — 2026-08-25

- Source visual truth:
  `C:/Users/47519/AppData/Local/Temp/codex-clipboard-3604b2b6-469b-4705-8dc3-76baecea8295.png`
  and
  `C:/Users/47519/AppData/Local/Temp/codex-clipboard-c499d8d1-41a8-47fd-b244-c31e7fb6b271.png`.
- Implementation evidence: in-app Browser capture of `http://127.0.0.1:1420/` at a 1280 x 720
  CSS viewport, device scale factor 1.25, empty Translate state. The capture is retained as the
  current browser task artifact rather than a repository asset.
- Full-view and focused-header comparison found no remaining P0, P1, or P2 mismatch. The focused
  check was necessary because the requested change concerns a 6 px header-density difference.
- The desktop header is reduced from 62 px to 56 px; compact layouts use 52 px.
- Workspace and content-page height calculations track the new header heights without introducing
  a gap or vertical overflow.
- Application chrome and static display copy use `user-select: none` so labels cannot be
  accidentally highlighted or copied during dragging and reading.
- Editable inputs, textareas, and future content-editable fields explicitly retain text selection,
  copy, paste, and editing behavior.
- Interaction checks: Translate navigation remained active; static workspace text computed to
  `user-select: none`; the source textarea computed to `user-select: text` and retained a full
  four-character keyboard selection.

## Final Result

passed
