# PaperTrans M7 desktop polish — Design QA

## Evidence

- Source visual truth: `D:\project_for_codex\clean_translate_for_pdf\frontend_tamplate\stitch_papertrans_ui\screen.png`
- User issue references:
  - `C:\Users\47519\AppData\Local\Temp\codex-clipboard-271f7573-2958-404c-8dbc-3e3592a07923.png`
  - `C:\Users\47519\AppData\Local\Temp\codex-clipboard-6a794233-e975-463a-97f7-6afe3fc8662b.png`
  - `C:\Users\47519\AppData\Local\Temp\codex-clipboard-b58eef4c-a7bd-4122-a28c-36bcec3ee939.png`
- Browser implementation: `D:\project_for_codex\clean_translate_for_pdf\tmp\design-qa-implementation-final.png`
- Menu state: `D:\project_for_codex\clean_translate_for_pdf\tmp\design-qa-menu-final.png`
- Collapsed settings state: `D:\project_for_codex\clean_translate_for_pdf\tmp\design-qa-collapsed-v2.png`
- Native frameless-window capture: `D:\project_for_codex\clean_translate_for_pdf\tmp\desktop-frameless-v2.png`
- Combined full-view comparison: `D:\project_for_codex\clean_translate_for_pdf\tmp\design-qa-comparison-final.png`
- Combined focused comparison: `D:\project_for_codex\clean_translate_for_pdf\tmp\design-qa-focused-final.png`
- Browser viewport: 1280 × 720 CSS px, device scale factor 1; implementation capture: 1280 × 720 px.
- Source template: 1600 × 1280 px. It represents the same desktop translation workspace at a taller aspect ratio, so full-view comparison was fit without cropping and proportion differences caused by viewport height were treated as intentional responsive behavior.
- Native capture: 1426 × 844 px on the Windows scaled desktop; used only to verify the absence of a native title bar and the visible Windows outer corner, not for pixel-level web-layout comparison.
- State: PDF empty state, Mock provider, OCR ready, settings expanded; focused evidence also covers provider menu open and settings collapsed.

## Findings

No actionable P0, P1, or P2 differences remain.

- Fonts and typography: Inter with Microsoft YaHei fallback preserves the template's compact sans-serif hierarchy. The 23 px brand, 14 px navigation, and small form labels remain legible without changing the intended density.
- Spacing and layout rhythm: the 50 px integrated header is visibly closer to the template; the three-surface workspace remains aligned. Cards retain 18 px outer radii. The collapsed settings bar is 54 px high and lets the PDF surface expand from about 342 px to 508 px at the QA viewport.
- Colors and tokens: the pale lavender/peach ambient surface, white glass cards, restrained gray borders, and indigo active states remain consistent with the source.
- Image and asset fidelity: the original ambient background asset and Material Symbols icon font are retained. No raster placeholders, CSS-drawn replacement icons, or low-resolution visual substitutions were introduced.
- Copy and content: the local task area is now labelled `仓库`; existing Chinese translation, OCR, privacy, and output language remain consistent.
- Interaction and accessibility: separators remain keyboard-operable. A pointer click without movement leaves the main split exactly unchanged (`571.2px 10px 628.8px` before and after). Switching translation, settings, PDF, and text states leaves the shell at `x=0`, width `1280`, and navigation at `x=562`. The custom provider control exposes combobox/listbox semantics and Escape/outside-click dismissal.
- Rounded surfaces: the settings outer card clips its scrollable content at an 18 px radius while the inner scrollbar is hidden (`scrollbar-width: none`). The custom provider popup has a 13 px radius and 9 px option radii.
- Desktop chrome: pywebview is configured as frameless with native shadow/Windows rounded-edge support. Integrated minimize, maximize/restore, and close controls occupy the header.

## Focused Comparison

The focused comparison was required because the original issues were localized and unreadable at full-view scale. It directly compares the reported scrollbar edge, native square provider popup, and tall/native header against the revised rounded card edge, rounded provider menu, and compact integrated header.

## Comparison History

1. Initial issue evidence showed a native scrollbar occupying the settings card's right edge, a square native select popup, a taller header/native Python frame, and splitters that moved on pointer-down.
   - Fixes: separated the rounded card shell from its hidden-scrollbar content; replaced the native provider select; changed splitter math to incremental pointer movement; enabled a frameless pywebview window and integrated controls.
   - Post-fix evidence: the settings shell reports 18 px radius and hidden overflow; pointer-only click produces a 0 px width change; the native capture shows a frameless outer Windows corner.
2. First custom-menu pass was still clipped by the settings card.
   - Fix: rendered the listbox through a document portal so the card can continue clipping its own scrolling content.
   - Post-fix evidence: all four provider options render outside the settings shell with rounded geometry.
3. First portal pass extended to 727.4 px in a 720 px viewport.
   - Fix: added viewport-aware upward placement with a conservative measured height allowance.
   - Post-fix evidence: the final menu occupies y=322.8–492.4 px and is fully visible.

## Primary Interactions Tested

- Pointer click on both resize affordances without drag.
- Keyboard resizing and threshold collapse of the lower settings surface.
- Click-to-expand restoration of settings.
- Provider menu open, selection, rounded geometry, and viewport avoidance.
- Translation/settings and PDF/text switching without horizontal shell movement.
- Browser console: no errors.
- Native desktop launch: frameless window and rounded Windows outer corner visible.

## Follow-up Polish

- P3: the maximize icon does not currently change glyph when the native window is maximized; behavior is correct, and the static glyph is acceptable for this milestone.

## Final Result

final result: passed
