# Library Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separate Library tab to browse saved documents by category and open a chosen document in the existing Dashboard viewer.

**Architecture:** `App` owns the active page and selected document ID, allowing Library to hand off a selection to Dashboard without coupling the two pages. Library fetches the existing saved-document API, offers category and text filters, and displays document cards with inline category icons. The library API gains an optional category filter based on the stored `label_name` field.

**Tech Stack:** React 19, TypeScript, Vite, FastAPI, SQLite, existing `/api/library` endpoints, CSS and inline SVG.

**Spec:** `docs/superpowers/specs/2026-11-20-library-tab-design.md`

## Global Constraints

- Keep the existing Dashboard search, chat, and viewer behavior intact.
- Use existing `/api/library` list and detail endpoints and finalized documents only.
- Filter categories using existing `label_name`; do not add or rewrite stored metadata.
- Selecting an item switches to Dashboard and loads the selected document there.
- Use inline SVG/CSS icons; do not add a dependency.
- Do not change document classification, storage, approval, or Dashboard layout.

## Review Focus

- Empty library: show a clear empty state without breaking category selection.
- Category with no matches: show a category-specific empty state and preserve the selected category.
- More than 20 documents: pagination must retain the active category and search query.
- Category names with underscores or unknown values: render a readable fallback label and generic icon.
- Failed list or category-filter request: show an error and allow the user to retry.

---

### Task 1: Add category filtering to the saved-document API

**Files:**
- Modify: `backend/api/library.py`

**Interfaces:**
- Consumes: existing `search_documents(q: str = "", offset: int = 0, limit: int = 20)` endpoint.
- Produces: same list response, with optional `label_name` query parameter that filters finalized documents before pagination.

- [ ] Add optional `label_name` query parameter to `search_documents`; when supplied, match the stored `label_name` exactly before applying offset and limit.
- [ ] Preserve existing text search behavior and response shape when `label_name` is absent.
- [ ] Manually inspect endpoint behavior for no filter, a matching category, an unknown category, and pagination combined with category filter.

### Task 2: Lift selected document handoff into `App`

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/components/Header.tsx`

**Interfaces:**
- `App` owns `activePage: 'dashboard' | 'upload' | 'library'` and `selectedDocumentId: string | null`.
- `DashboardPage` receives optional `selectedDocumentId` and `onDocumentOpened(documentId: string)` props; when the ID changes, it loads that document using its existing detail request.
- `Header` receives the expanded page union and renders Dashboard, Library, and Upload navigation.

- [ ] Extend active page navigation with `library` and retain the existing header status display.
- [ ] Pass the selected document ID from `App` into Dashboard; keep the existing Dashboard list search and document-loading behavior available.
- [ ] When a document is selected from Library, set the ID and navigate to Dashboard; Dashboard fetches and renders it with existing `DocumentViewer` and `ChatPanel` behavior.
- [ ] Ensure returning from Library to Dashboard without a new selection keeps the already selected Dashboard document.

### Task 3: Build the dedicated Library page

**Files:**
- Create: `frontend/src/pages/LibraryPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.css`

**Interfaces:**
- `LibraryPage` receives `onSelectDocument(documentId: string) => void`.
- List requests use `/api/library?q=...&label_name=...&offset=...&limit=20` and consume `{ items, total }`.
- Document item fields: `document_id`, `name`, `label_name`, `page_count`, `created_at`.

- [ ] Add a standalone Library page with title, search input, category dropdown (default “Tất cả”), refresh control, responsive document-card list, loading/error/empty states, and pagination.
- [ ] Populate category choices from the existing labels endpoint; display friendly Vietnamese names for common categories such as `letter` and `document`, with a readable fallback for other labels.
- [ ] Add decorative inline SVG category icons with a generic fallback icon.
- [ ] Preserve query, category, and offset in list requests; reset offset when query or category changes.
- [ ] Wire document-card selection to `onSelectDocument`, returning the user to Dashboard with the selected document ID.
- [ ] Add responsive styles consistent with existing colors, spacing, and card treatments; do not change Dashboard layout.

### Task 4: Build and review the completed flow

**Files:**
- Review: `backend/api/library.py`
- Review: `frontend/src/App.tsx`
- Review: `frontend/src/pages/DashboardPage.tsx`
- Review: `frontend/src/pages/LibraryPage.tsx`
- Review: `frontend/src/components/Header.tsx`
- Review: `frontend/src/App.css`

- [ ] Run `npm run build` from `frontend/` and resolve TypeScript or bundling errors.
- [ ] Review the flow manually: navigate Library, filter categories, paginate/search, choose a document, and confirm Dashboard displays its saved content and chat context.
- [ ] Review empty and failed request states and confirm the existing Dashboard search still works.
