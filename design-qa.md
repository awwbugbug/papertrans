# PaperTrans unified desktop workspace — Design QA

## Evidence

- Source visual truth: `D:\project_for_codex\clean_translate_for_pdf\frontend_tamplate\stitch_papertrans_ui\screen.png`
- User header target: `C:\Users\47519\AppData\Local\Temp\codex-clipboard-3985eee4-2bf0-4ad0-b8f3-e73827a6ee3b.png`
- Browser-rendered implementation: `C:\Users\47519\AppData\Local\Temp\papertrans-unified-browser.png`
- Native desktop capture: `C:\Users\47519\AppData\Local\Temp\papertrans-native-unified.png`
- Combined full-view comparison: `C:\Users\47519\AppData\Local\Temp\papertrans-design-qa-full.png`
- Combined focused header comparison: `C:\Users\47519\AppData\Local\Temp\papertrans-design-qa-header.png`
- Browser viewport: 1280 × 720 CSS px at device scale factor 1.25; implementation capture: 1280 × 720 px.
- Source template: 1600 × 1280 px, normalized to 1280 × 1024 without cropping for the combined comparison.
- User header target: 1920 × 60 px, normalized to 1280 × 40 for the focused comparison.
- State: translation empty state, Mock provider, OCR ready, all five workspace surfaces expanded.

## Findings

No actionable P0, P1, or P2 differences remain.

- Fonts and typography: the compact sans-serif hierarchy, 23 px brand, 14 px navigation, and small form labels remain consistent with the source visual language. Text input, character count, empty states, and collapsed-bar labels remain legible.
- Spacing and layout rhythm: the 50 px integrated header matches the compact target. The navigation center is exactly 640 px in the 1280 px viewport, independent of the 119.84 px brand and 132 px window controls. The new text surfaces intentionally extend the source template into a five-surface workspace without breaking the original left/right reading hierarchy.
- Colors and visual tokens: the pale lavender/peach ambient background, white cards, restrained borders, indigo active states, 18 px card radii, and subtle shadows remain consistent with the Stitch source.
- Image and asset fidelity: the existing background treatment and Material Symbols icon font are retained. No raster placeholders, handcrafted SVG substitutions, emoji, or CSS-drawn replacement icons were introduced.
- Copy and content: the top navigation uses `仓库 / 翻译 / 设置`; PDF/text mode switching and the `本地桌面运行` label are absent. Text translation is explicitly marked as the next M7.2 integration rather than appearing falsely functional.
- Interaction and accessibility: all three internal separators remain keyboard-operable. Both text surfaces collapse at the threshold to a 46 px bar and restore by click. The settings surface collapses to a 52 px bar and restores by click. Text input updates its character count. Navigation remains centered at 640 px and document width remains 1280 px across translation, settings, warehouse, and return-to-translation states.
- Native window behavior: a live pywebview run verified left-edge resizing (width 1413 → 1333 px), maximize state, drag-down restore, and DWM corner preference changes from non-rounded while maximized to rounded after restore.
- Console: no browser console errors were recorded.

## Focused Comparison

The focused header comparison was required because the user-reported alignment issue occupies only 60 px and is not readable in the full-view board. It shows the source and implementation navigation centered on the same normalized viewport, with the implementation preserving the integrated controls on the right.

## Comparison History

1. User evidence showed navigation visually offset to the right and requested normal Windows resizing/restoration behavior plus a unified text/PDF workspace.
   - Fixes: centered navigation independently of adjacent content; added native Windows resize/move handling and DWM corner-state synchronization; rebuilt the translation screen as five vertically and horizontally adjustable surfaces.
   - Post-fix evidence: measured navigation center is 640 px in a 1280 px viewport; live window probes confirm edge resize, maximize, drag-down restore, and rounded restore state; the combined implementation capture shows all five surfaces in one screen.
2. Interaction pass exercised threshold collapse and restoration for the source-text, translated-text, and settings surfaces.
   - Post-fix evidence: source and translated text grids resolve to `46px 10px 578px` when collapsed; settings resolves to `412.763px 10px 52px`; all restore via their collapsed bars.

## Primary Interactions Tested

- Native left-edge window resize.
- Maximize followed by dragging the header downward to restore.
- Rounded-corner preference in normal and maximized states.
- Source-text and translated-text keyboard resize, threshold collapse, and click-to-expand.
- Settings keyboard resize, threshold collapse, and click-to-expand.
- Text entry and character-count update.
- Translation/settings/warehouse navigation without horizontal shell shift.
- Browser console error check.

## Follow-up Polish

- P3: the text translation result surface is intentionally an empty-state placeholder until M7.2 connects it to the existing provider/protection layer.

## Final Result

final result: passed
