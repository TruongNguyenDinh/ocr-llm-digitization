# Manual formula correction in OCR review

## Requirement

LLM correction must preserve OCR formulas. Human reviewers may correct scanned formulas before final approval. Both review panels must remain synchronized, with manual highlighting and before/after audit records.

## Existing issue

`markdown_review.py` rejects protected-span edits for both automated suggestions and manual preview/finalization. `ReviewModal.tsx` exposes a plain-text editor for the entire page, so there is no dedicated formula control.

## Proposed interaction

In Edit mode, show ordinary text and formula controls separately in document order. Each formula control contains its editable LaTeX body and a rendered preview. Preserve the existing inline `$...$` or display `$$...$$` wrapper and the formula's place in the document. Match formulas between panels by their source occurrence, including repeated formulas. Applying a formula change updates both panels, highlights both as manual edits, and records the original and replacement formula in the existing audit log.

Reject invalid LaTeX with a visible error. Preserve the user's draft while allowing correction or cancellation; prevent saving until the formula is valid. Ordinary text editing must not accidentally remove a formula or change its wrapper.

## Backend behavior

Keep automated formula preservation in the LLM workflow. Add a distinct manual mapping path used by both preview and finalization. Validate formula count, order and wrapper type; replace formula bodies as LaTeX without Markdown escaping. Continue protecting links, HTML, code and surrounding Markdown structure. The saved Markdown must contain the exact approved formula used in the preview. Finalization still requires an explicit user save.

## Approaches

1. Dedicated LaTeX field with rendered preview (recommended): uses the existing math renderer and makes the editable source explicit.
2. Edit LaTeX inside the whole-page textarea: smaller UI change, but leaves delimiters and formulas mixed with prose.
3. Add a graphical equation editor: larger dependency and interaction change; defer until requested.

The recommended approach is a proposal, not yet approved.

## Verification

Check inline and display formulas, duplicate formulas, multiline LaTeX, edits from either panel, preview/save equality, manual highlight color and audit history. Confirm that LLM suggestions still cannot modify formulas, and that manual edits cannot alter unrelated Markdown structure. Use temporary storage for save verification; do not approve the user's actual review during testing.
