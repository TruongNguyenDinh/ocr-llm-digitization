# Web OCR Review with Gemini, Qwen, and Final Approval — Design

## Intent

After OCR and LLM correction, open a floating review window with OCR output and corrected output side by side. This is the final human check: choosing either Save action immediately finalizes the document in the existing storage archive.

## User flow

1. After OCR completes, choose Gemini (default) or Qwen3:8B and start correction.
2. When correction completes, open a two-column review window. Scroll position is synchronized between columns.
3. Highlight text changed by the LLM in one color. Edit either column; apply the user's text edit to the corresponding text in the other column, highlight the manual edit in a second color, and append a before/after audit entry.
4. `Save with OCR output` finalizes the OCR-side content and `Save with LLM output` finalizes the LLM-side content. `Edit` toggles editing. `Cancel` closes the review without finalizing.

## Structure preservation

The LLM continues to receive only ordered plain text from OCR JSON blocks. Its changes are mapped back onto the OCR Markdown text nodes. Markdown block/inline structure, ordering, tables, headings, formulas, and image references remain intact. Review editing changes text nodes only; it cannot change Markdown structure. If a text correction cannot be mapped unambiguously, report an error rather than silently rewriting the page structure.

## Providers

- Gemini is selected by default and called through the Gemini API with a backend-only `GEMINI_API_KEY`; default model is `gemini-3.8-flash`, configurable with `GEMINI_MODEL`.
- Qwen3:8B is selectable explicitly and called through the existing Ollama client using `OLLAMA_BASE_URL` and `OLLAMA_MODEL` (default `qwen3:8b`).
- No automatic provider fallback. Provider errors are shown directly without exposing credentials.
- Both providers share the existing correction prompt, metadata extraction, schema validation, and review data format.

## Persistence

- Generate a pending review draft and its page comparisons in `data/raw/{document_name}/review.json`.
- Keep the uploaded original under `data/raw/{document_name}/_source.{ext}` after OCR so finalization can archive it; copy any relative image assets referenced by the approved Markdown into the final digitization directory.
- Store manual edit history with timestamp, page, source side, affected text, and before/after values in the review record and copy it into final digitization storage as an audit log.
- On Save, call the existing `finalize_review` flow with selected page text and extracted metadata. Finalized document pages retain OCR Markdown structure; original source PDF/image is archived as before.
- The current UI has no authentication/user profile. Use `DIGITIZATION_USER_ID` with default `local_user` until auth exists.
- Cancel closes without finalizing; review draft stays pending so OCR/LLM data is not lost.

## Approaches considered

1. Structure-preserving side-by-side review over Markdown text nodes — selected. It keeps the OCR layout while allowing synchronized edits and a complete audit trail.
2. Plain-text diff editor — rejected because it loses the OCR-generated document structure in the final artifact.
3. Keep model selection only and create a separate approval flow — rejected because the user confirmed this is the final review step.

## Scope and constraints

Add a Gemini client and provider selector, generate reviews from completed OCR output, build the synchronized final-review window, persist edit history, and expose immediate finalization through the existing storage service. Do not expose secrets, silently switch providers, permit Markdown structure edits, auto-approve, or change OCR and LoRA workflows.

## Implementation calls

- Use Google's current Gemini GenerateContent REST API with structured JSON output.
- A manual edit updates the matching aligned text span on both sides; preserve all unrelated LLM corrections. The user-edited span takes precedence on both sides and is recorded once per edit action.
- The floating window is modal and owns synchronized scrolling; `Cancel` leaves the generated review pending.
