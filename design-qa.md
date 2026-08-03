# PaperTrans normal-window top-border fix — Design QA

## Evidence

- Source visual truth and issue reference: `C:\Users\47519\AppData\Local\Temp\codex-clipboard-eda268a4-b7c0-4592-80df-85031e625d0c.png`
- Final native implementation capture: `C:\Users\47519\AppData\Local\Temp\papertrans-border-final-full.png`
- Final focused header capture: `C:\Users\47519\AppData\Local\Temp\papertrans-border-final-screen.png`
- Combined focused comparison: `C:\Users\47519\AppData\Local\Temp\papertrans-black-border-comparison.png`
- Issue reference size: 318 × 80 px.
- Implementation capture size: 1080 × 720 px; focused comparison uses an unscaled 318 × 80 px crop from its top-left corner.
- State: Windows normal/restored window, translation empty state, native DWM rounding enabled.
- Density normalization: no resampling was applied to the focused 318 × 80 comparison crop.

## Findings

No actionable P0, P1, or P2 differences remain.

- Fonts and typography: the PaperTrans brand retains the same family, weight, hierarchy, and antialiasing; the fix does not alter web content.
- Spacing and layout rhythm: the corrected client surface begins at the rounded top edge without the prior dark inset strip. Header height, brand padding, navigation alignment, cards, and splitters are unchanged.
- Colors and visual tokens: the pale lavender header now reaches the rounded window edge. The dark line visible in the issue reference is absent; the captured top-edge pixel is the header color `rgb(247, 244, 252)`.
- Image and asset fidelity: no icons, background assets, fonts, or raster content changed.
- Copy and content: no text or interface labels changed.
- Window behavior: live native verification confirms normal state has no `WS_THICKFRAME`; left-edge resizing still changes the window width; the style is removed again after resizing; maximized state temporarily retains the style so drag-down restore continues to work; restored state returns to rounded corners with no permanent resize frame.

## Full-View And Focused Comparison

The source evidence is intentionally a focused 318 × 80 defect crop, so there is no source full-app frame for pixel-level comparison. The 1080 × 720 final native capture was inspected for surrounding regressions, while the required same-input visual comparison uses the exact affected top-left region. The comparison shows the issue strip on the left and the corrected uninterrupted lavender surface on the right.

## Comparison History

1. Initial reproduction showed `WS_THICKFRAME` permanently present (`0x160F0000`) and a dark non-client strip above the header.
   - Minimal experiment: removed only `WS_THICKFRAME` and refreshed the native frame.
   - Result: the dark strip disappeared, confirming the root cause.
2. Removing the style permanently made maximized drag-down restoration fail.
   - Fix: keep `WS_THICKFRAME` absent in normal state, enable it temporarily during native resize loops, retain it while maximized, and remove it on restore.
   - Post-fix evidence: edge resize succeeds; normal and post-resize styles have no thick frame; maximized drag-down restores successfully; restored DWM corner preference is `ROUND`.
3. The normal DWM outline still contributed a one-pixel dark edge after the thick frame was removed.
   - Fix: set `DWMWA_BORDER_COLOR` to `DWMWA_COLOR_NONE` together with the window-state update.
   - Post-fix evidence: the final top-edge pixel matches the lavender header and the focused comparison contains no dark line on the corrected implementation.

## Primary Interactions Tested

- Normal-window visual capture with rounded top edge.
- Left-edge resize and post-resize style cleanup.
- Maximize state and non-rounded DWM preference.
- Dragging a maximized header downward to restore.
- Restored rounded-corner preference and thick-frame cleanup.

## Follow-up Polish

No remaining P3 finding for this focused fix.

## Final Result

final result: passed
