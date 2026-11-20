# Library tab design

## Intent

Add a dedicated Library tab so users can browse finalized documents without adding more controls to Dashboard. Selecting a document takes the user to Dashboard and opens that document's saved content in the existing viewer.

## Scope and constraints

- Keep the existing Dashboard search, chat, and viewer behavior intact.
- Add a separate Library page with a category dropdown, category icons, document list, and document selection.
- Use the existing `/api/library` list and detail endpoints and finalized documents only.
- Filter categories using the existing `label_name` values (for example, letter, document, report), with an All option. Show friendly Vietnamese labels in the UI; do not add or rewrite stored metadata.
- Selecting an item switches to Dashboard and loads the selected document there.

## Approaches

1. Dedicated Library page and shared selection state in `App`: selected. It keeps browsing separate and connects selection to the existing Dashboard viewer.
2. Keep browsing on Dashboard and add a Library navigation alias: rejected because it duplicates the current Dashboard behavior and adds controls to the screen the user wants to keep uncluttered.

## Implementation calls

- Add iconography with small inline SVG/CSS icons; avoid a new dependency.
- Preserve current API pagination and search behavior where practical; add category filtering to Library using the data returned by the existing endpoint.
- Use the selected `document_id` as the handoff to Dashboard, which remains responsible for fetching and rendering the document.

## Out of scope

Changing document classification, storage, approval, or Dashboard layout.
