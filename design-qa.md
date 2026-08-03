# M7 desktop workspace design QA

## Evidence

- Source visual truth: `frontend_tamplate/stitch_papertrans_ui/screen.png`
- Implementation screenshot: `tmp/design-qa-implementation.png`
- Combined comparison: `tmp/design-qa-comparison.png`
- Reference pixels: 1600 x 1280.
- Implementation capture: 1280 x 720 CSS pixels at device scale 1 in the in-app browser.
- State: the reference is the empty PDF state; the implementation capture is the completed Mock-translation state for `test_pdf/1504.08083v2.pdf`. The comparison therefore evaluates the shared visual system and workspace proportions rather than pixel-identical content.

## Full-view comparison

- The restrained header, centered navigation, pale lavender/peach ambient background, translucent white cards, indigo active state, typography hierarchy, radii, and shadows remain consistent with the reference.
- The requested product change is visible: the original PDF occupies the former upload card, while the translated PDF occupies the right card. The settings card is materially shorter than the source-document card.
- The page shell keeps a fixed viewport width. Measured `documentElement.clientWidth`, header width, and page width remained 1280 px when switching PDF to text and translation to settings, with no document-level horizontal overflow.

## Focused evidence

- Source card: uploaded PDF renders inline with a compact filename/page toolbar and replace/remove controls.
- Translation card: completed output renders inline on the right with its own completion toolbar and quality strip; the former nested two-PDF grid is gone.
- Resizing: the vertical PDF workspace separator changed computed columns from `561.2 / 10 / 638.8 px` to `585.6 / 10 / 614.4 px`; the text separator changed from `610 / 10 / 590 px` to `634.4 / 10 / 565.6 px`. The horizontal separator is also keyboard-accessible and remains bounded so neither card can collapse.
- Interaction checks: PDF/text switching, settings/translation navigation, PDF upload, Mock translation completion, original PDF rendering, output PDF rendering, and keyboard resizing all passed. Browser console warnings/errors: none.

## Required fidelity surfaces

- Fonts and typography: Inter with Microsoft YaHei fallback remains consistent; labels and document toolbars use compact optical sizing without changing the main hierarchy.
- Spacing and layout rhythm: the upload/source card is now the dominant left surface, the settings card is compact, and the two subtle resize gutters preserve the original 20 px visual rhythm without appearing as extra cards.
- Colors and tokens: existing neutral, lavender, indigo, success-green, border, and shadow tokens are preserved.
- Image and asset quality: the supplied ambient background and Material Symbols icon font remain intact; both PDFs are rendered by the browser PDF surface rather than placeholders.
- Copy and content: Simplified Chinese labels are retained and the new toolbar labels describe real actions.

## Comparison history

1. Initial implementation showed an equal-height source/settings split at the 720 px test height because both grid rows hit their minimums; the settings card also exposed only part of the primary action.
2. Reduced the protected row minimums, tightened short-window settings spacing, and hid the nonessential privacy footnote only below 790 px. Post-fix evidence shows a larger source reader, a shorter scrollable settings card, and working horizontal resizing.

## Findings

- No actionable P0, P1, or P2 issues remain for the four requested changes.
- P3: at the minimum 720 px window height, advanced provider fields require scrolling inside the settings card. This is intentional so the PDF reader remains useful and all controls stay reachable.

## Final result

final result: passed
