# Manual formula editing implementation plan

> Execute natively in the existing workspace as previously requested.

**Goal:** Humans can correct formulas while LLM edits remain text only.
**Architecture:** Add an explicit manual Markdown mapping function; map formulas by source occurrence and retain delimiters. Separate formula fields from prose in Edit mode, using the existing math renderer for validation and preview.
**Tech stack:** Python, React, TypeScript, existing KaTeX/remark stack.
**Spec:** `docs/superpowers/specs/2026-11-05-manual-formula-editing-design.md`, confirmed by the user.

## Constraints

Preserve document structure, formula placement and inline/display style. Keep both panels synchronized, orange manual highlights and before/after logs. Preview and save use the same mapping. Never finalize a real document during verification.

## Tasks

- [x] Backend: add manual formula mapping to `backend/llm/markdown_review.py`; use it in preview and finalization. Verified formulas, duplicate occurrences, prose edits alongside math, and strict LLM formula protection (`python -m unittest discover -s tests -v`: 7 passed).
- [x] Frontend: add formula parsing/editor components; integrate into `ReviewModal.tsx`. Matched formula edits by occurrence, kept invalid LaTeX draft visible and disabled saving until applied/cancelled. Verified inline/display, duplicates, code exclusions and synchronized updates/logging.
- [x] Verified KaTeX manual highlights, preview/finalize parity with temporary storage, and frontend production build.

## Review focus

Repeated identical formulas must update the correct occurrence. Invalid or incomplete LaTeX must not lose drafts. Formula edits must not introduce Markdown delimiters or change HTML/code/links. Formula highlight must survive KaTeX rendering. Saving either side must retain the same approved math and audit history.
