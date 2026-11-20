# Web OCR Review with Gemini, Qwen, and Final Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide Gemini-default/Qwen-selectable OCR correction and a final side-by-side review modal that preserves OCR Markdown, logs manual edits, and finalizes immediately when the user saves.

**Architecture:** Add a Gemini GenerateContent REST client implementing the existing Ollama chat boundary. Generate provider-neutral review drafts from OCR plain text, map LLM edits onto original Markdown text nodes, then let a modal edit aligned text nodes on both sides while preserving Markdown structure. Save calls the existing transactional storage service with selected page Markdown and audit history.

**Tech Stack:** FastAPI, Python `urllib`, React, TypeScript, existing `react-markdown`/remark stack, Gemini REST API, Ollama API, SQLite/file storage.

**Spec:** `docs/superpowers/specs/2026-10-29-web-ocr-correction-gemini-qwen-design.md`

## Global Constraints

- Gemini is the default (`GEMINI_MODEL=gemini-3.8-flash`) and its key is backend-only (`GEMINI_API_KEY`).
- Qwen3:8B remains selectable via Ollama; never automatically switch provider.
- LLM input remains ordered plain text from OCR JSON blocks (`page_*.txt`).
- Final pages preserve original OCR Markdown structure; only text nodes may change.
- Save finalizes the selected side through `finalize_review`; Cancel leaves the draft pending.
- Keep timestamped manual edit history in `review.json` and final digitization storage.
- Use `DIGITIZATION_USER_ID`, default `local_user`, because no web authentication exists.
- Preserve existing user changes and do not touch `backend/LoRA/`.
- Do not add or run tests unless the user requests verification. The user previously requested an npm build, so run the frontend production build before delivery.
- Retain the uploaded original in the raw document directory after OCR and copy relative Markdown image assets during finalization so the archived Markdown remains usable.

## Review Focus

- Missing/invalid Gemini key, API quota, and malformed JSON: show useful errors without leaking credentials or falling back to Qwen.
- Ollama unavailable or Qwen missing: show the Ollama error with no provider switch.
- Missing/malformed OCR text or ambiguous mapping: reject the review instead of changing Markdown structure silently.
- Manual edit mapping across different OCR/LLM text: update both corresponding text nodes, preserve unrelated corrections, and log one before/after action.
- Duplicate save, invalid review ID, or missing source file: do not create partial final storage or mark review finalized.

---

### Task 1: Provider clients and review schema

**Files:**
- Create: `backend/llm/gemini_client.py`
- Modify: `backend/llm/workflow.py`
- Modify: `backend/llm/schemas.py`
- Modify: `backend/llm/ollama_client.py` only if it needs a model override

**Interfaces:**
- `GeminiClient.chat(messages, response_format=None) -> str`, configured by `GEMINI_API_KEY`/`GEMINI_MODEL`.
- `LocalLLMWorkflow(client, provider, model).process_pages(...) -> ReviewDraft` accepts Gemini or Ollama chat clients.
- `ReviewDraft` serialization records provider and model.

- [x] Add Gemini REST calls with the API key in `x-goog-api-key`, structured JSON generation, bounded timeout, and redacted errors.
- [x] Make provider/model explicit in `LocalLLMWorkflow`; keep Qwen3:8B selectable via Ollama and preserve shared prompt/schema validation.

### Task 2: Preserve Markdown and create aligned review data

**Files:**
- Create: `backend/llm/markdown_review.py`
- Modify: `backend/document_workflow.py`
- Modify: `backend/llm/comparison.py`
- Modify: `backend/llm/review_store.py`

**Interfaces:**
- `build_markdown_review(raw_markdown: str, raw_text: str, corrected_text: str) -> MarkdownReview` returns structured Markdown plus text-only change spans.
- Review pages contain OCR Markdown, LLM Markdown, and their text-node alignment; block structure is fixed.

- [x] Parse Markdown and map LLM's text-only corrections onto text nodes using conservative alignment; fail on ambiguous mapping.
- [x] Preserve headings, tables, formulas, image references, list/block structure, and source order; store Markdown variants and LLM highlights with the review.

### Task 3: Review and finalization API

**Files:**
- Modify: `backend/api/app.py`
- Modify: `backend/storage/service.py`
- Modify: `backend/llm/review_store.py`

**Interfaces:**
- `POST /api/llm/reviews` accepts `{document_name, provider}` and returns review ID, pages, metadata, provider/model, and LLM spans.
- `POST /api/llm/reviews/{review_id}/finalize` accepts `{source: "ocr" | "llm", approved_pages, edit_log}` and returns the stored document ID/paths.

- [x] Validate request fields, provider, document/review roots, pending status, and exact page IDs.
- [x] Persist audit entries (time, page, editor side, before/after text) in the review and copy them to final storage as `edit_log.json` within the same rollback-safe finalization path.
- [x] Call `finalize_review` with configured `DIGITIZATION_USER_ID` (default `local_user`) and selected page Markdown. Reject duplicate/invalid finalization without partial output.

### Task 4: Side-by-side final review modal

**Files:**
- Create: `frontend/src/services/llmApi.ts`
- Create: `frontend/src/components/ReviewModal.tsx`
- Modify: `frontend/src/components/CorrectionControls.tsx`
- Modify: `frontend/src/pages/UploadPage.tsx`
- Modify: `frontend/src/App.css`

**Interfaces:**
- `createReview(documentName, provider)` returns typed review content and highlighting spans.
- `finalizeReview(reviewId, source, approvedPages, editLog)` finalizes selected content.
- `ReviewModal` receives review pages, metadata, on-save, and on-cancel callbacks.

- [x] Make Gemini the default selector and enable correction after OCR completion; show processing/error state.
- [x] Open a floating, two-column modal with synchronized scroll, rendered OCR/LLM structure, and separate LLM/manual-edit highlight colors.
- [x] `Edit` enables text-node changes only; mirror each edit to the aligned node in the other pane and append a timestamped before/after audit entry.
- [x] `Save with OCR output` and `Save with LLM output` finalize immediately; `Cancel` closes without finalizing and retains the pending draft.

### Task 5: Setup and workflow documentation

**Files:**
- Modify: `README.md`

- [x] Document backend-only `GEMINI_API_KEY`, `GEMINI_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and `DIGITIZATION_USER_ID` setup; use placeholders only.
- [x] Document the provider choice, structure-preserving final review, audit log, immediate save, and cancel behavior.

### Completion notes

The repository has no configured automated test suite. No tests were added or run. The frontend production build was run because the user had previously asked for it.
