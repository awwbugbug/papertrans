# M7.1 Design QA

Result: passed

## Visual target

- Reference: `frontend_tamplate/stitch_papertrans_ui/screen.png`
- Implementation: `frontend/src/App.tsx` and `frontend/src/styles.css`
- Verification viewport: 1600 × 1280, matching the reference image.

## Comparison

- Preserved the reference composition: restrained top navigation, left upload/configuration stack, large right preview surface, pale lavender/peach ambient background, translucent cards, indigo active state, and compact form controls.
- Kept the upload region and empty preview as the dominant surfaces; functional additions use the same visual language and do not displace the primary hierarchy.
- Verified PDF/text switching, text entry, settings navigation, provider selection, compatible API address visibility, and empty-state rendering in the in-app browser.
- Browser console contains no warnings or errors in the verified state.

## Intentional differences

- UI text is localized to Simplified Chinese.
- `Mock 版式测试` is the safe default; external providers require explicit selection.
- The input-mode selector and local-runtime indicator are visible because the product now supports both PDF and text workflows inside one desktop window.
- API key and model fields appear only for providers that require them, reducing empty-state density.

## Deferred

- The text pane is interactive but provider execution is M7.2.
- PDF.js paragraph selection, dual-pane correspondence, word selection, and synchronized scrolling are M7.3.
- Windows installer packaging follows after the interaction model is stable.
