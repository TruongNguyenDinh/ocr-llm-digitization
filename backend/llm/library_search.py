"""LLM-assisted hybrid search across finalized library documents."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import math
from pathlib import Path
from typing import Any, Sequence

from backend.storage.repository import SQLiteRepository
from .document_chat import MAX_DOCUMENT_CONTEXT_BYTES, _normalize, _terms
from .document_index import split_markdown_pages
from .embedding_client import OllamaEmbeddingClient
from .ollama_client import OllamaClient
from .prompts import LIBRARY_ANSWER_SYSTEM_PROMPT, SEARCH_QUERY_SYSTEM_PROMPT
from .vector_store import LocalPassageIndex, ScoredPassage

_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {key: {"type": "array", "items": {"type": "string"}}
                   for key in ("terms", "entities", "dates", "identifiers")},
    "required": ["terms", "entities", "dates", "identifiers"],
}
_CAPITALIZED_PHRASE = re.compile(r"\b[A-ZÀ-ÖØ-ÞĐ][^\W\d_]*(?:\s+[A-ZÀ-ÖØ-ÞĐ][^\W\d_]*)+\b")
_PERSON_TITLE_PREFIX = re.compile(
    r"^(?:ong|ba|thu tuong|pho thu tuong|chu tich nuoc|chu tich|pho chu tich|"
    r"tong bi thu|bi thu|bo truong|thu truong|giam doc|pho giam doc|"
    r"giao su|pho giao su|tien si|bac si)\s+"
)


def _entity_pattern(entity: str) -> re.Pattern[str]:
    """Match a full entity or its name without leading personal titles.

    A signature may put the title on a separate line after the name, while
    query extraction includes it before the name. Never drop arbitrary name
    tokens: unrelated people sharing a surname must remain excluded.
    """
    normalized = " ".join(_normalize(entity).split())
    variants = [normalized]
    name = normalized
    while True:
        stripped = _PERSON_TITLE_PREFIX.sub("", name, count=1)
        if stripped == name or len(stripped.split()) < 2:
            break
        variants.append(stripped)
        name = stripped
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(value) for value in variants) + r")(?!\w)")


@dataclass(frozen=True)
class SearchTerms:
    original_query: str
    terms: list[str]
    entities: list[str]
    dates: list[str]
    identifiers: list[str]

    @property
    def enriched_query(self) -> str:
        extracted = self.terms + self.entities + self.dates + self.identifiers
        return " ".join([self.original_query, *dict.fromkeys(extracted)])


@dataclass(frozen=True)
class SearchResult:
    document_id: str
    document_name: str
    page_number: int
    snippet: str
    score: float


@dataclass(frozen=True)
class SearchPage:
    results: list[SearchResult]
    total: int
    page: int
    page_size: int
    extracted_terms: SearchTerms


@dataclass(frozen=True)
class GroundedAnswer:
    answer: str
    citations: list[SearchResult]
    model: str
    context_used_bytes: int


def _clean_extracted(values: Any, question: str) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized_question = _normalize(question)
    result = []
    for value in values:
        if not isinstance(value, str):
            continue
        value = " ".join(value.split()).strip()
        if value and _normalize(value) in normalized_question and value not in result:
            result.append(value)
    return result


def extract_search_query(question: str, client: OllamaClient | None = None) -> SearchTerms:
    if not question.strip():
        raise ValueError("Nhập nội dung cần tìm kiếm.")
    model = client or OllamaClient()
    try:
        response = model.chat([
            {"role": "system", "content": SEARCH_QUERY_SYSTEM_PROMPT},
            {"role": "user", "content": question.strip()},
        ], response_format=_EXTRACTION_SCHEMA)
        payload = json.loads(response)
        if not isinstance(payload, dict):
            raise ValueError("Query extraction must be an object")
        terms = _clean_extracted(payload.get("terms"), question)
        entities = _clean_extracted(payload.get("entities"), question)
        dates = _clean_extracted(payload.get("dates"), question)
        identifiers = _clean_extracted(payload.get("identifiers"), question)
        term_values = {_normalize(value) for value in terms}
        known_entities = {_normalize(value) for value in entities}
        inferred_entities = [
            match.group(0).strip() for match in _CAPITALIZED_PHRASE.finditer(question)
            if _normalize(match.group(0)) in term_values
            and not any(_normalize(match.group(0)) in entity or entity in _normalize(match.group(0))
                        for entity in known_entities)
        ]
        entities = list(dict.fromkeys([*entities, *inferred_entities]))
        if not any((terms, entities, dates, identifiers)):
            terms = sorted(_terms(question))
    except (ValueError, TypeError, json.JSONDecodeError):
        terms, entities, dates, identifiers = sorted(_terms(question)), [], [], []
    return SearchTerms(question.strip(), terms, entities, dates, identifiers)


class LibrarySearchService:
    def __init__(self, repository: SQLiteRepository, vector_index: LocalPassageIndex,
                 embedder: OllamaEmbeddingClient, extraction_client: OllamaClient | None = None,
                 *, storage_root: str | Path, vector_score_threshold: float | None = None) -> None:
        self.repository, self.vector_index, self.embedder = repository, vector_index, embedder
        self.extraction_client = extraction_client or OllamaClient()
        self.storage_root = Path(storage_root).resolve()
        self.vector_score_threshold = (float(os.environ.get("OLLAMA_VECTOR_SCORE_THRESHOLD", "0.35"))
                                       if vector_score_threshold is None else vector_score_threshold)

    def _read_pages(self, row: dict[str, Any]) -> list[str]:
        pages = []
        for filename in row["digitized_page_paths"]:
            path = Path(filename).resolve()
            if path.is_relative_to(self.storage_root) and path.is_file():
                pages.append(path.read_text(encoding="utf-8"))
            else:
                pages.append("")
        return pages

    def search_library(self, question: str, page: int = 0, page_size: int = 20) -> SearchPage:
        extracted = extract_search_query(question, self.extraction_client)
        rows = self.repository.list_finalized_documents()
        documents = {str(row["document_id"]): row for row in rows}
        indexed_document_ids = {
            document_id for document_id, row in documents.items()
            if row.get("index_status") == "indexed"
        }

        # If the question names a person, organization, or place, keep retrieval
        # inside documents that actually mention that entity. This prevents
        # common words such as "phải" and "chịu" from surfacing unrelated files.
        entity_patterns = [_entity_pattern(value) for value in extracted.entities if value.strip()]
        entity_documents: set[str] = set()
        if entity_patterns:
            for document_id, row in documents.items():
                full_text = " ".join(_normalize("\n".join(self._read_pages(row))).split())
                if any(pattern.search(full_text) for pattern in entity_patterns):
                    entity_documents.add(document_id)
            documents = {key: row for key, row in documents.items() if key in entity_documents}

        vector_results: list[ScoredPassage] = []
        if indexed_document_ids and documents and self.vector_index.count():
            vector = self.embedder.embed([extracted.enriched_query])[0]
            vector_results = self.vector_index.search(
                vector, limit=self.vector_index.count(), score_threshold=self.vector_score_threshold)
        candidates: dict[tuple[str, int, int, str], tuple[str, float, float]] = {}
        for item in vector_results:
            if item.document_id in documents and item.document_id in indexed_document_ids \
                    and item.score >= self.vector_score_threshold:
                key = (item.document_id, item.page_number, item.chunk_index, item.content_hash)
                candidates[key] = (item.text, item.score, 0.0)

        query_terms = set(_terms(" ".join([extracted.original_query, extracted.enriched_query])))
        for entity in extracted.entities:
            query_terms.update(re.findall(r"[a-z0-9]+", _normalize(entity)))
        normalized_question = _normalize(extracted.original_query)
        all_passages: list[tuple[str, Any]] = []
        for document_id, row in documents.items():
            all_passages.extend((document_id, passage)
                                for passage in split_markdown_pages(self._read_pages(row)))

        frequencies: dict[str, int] = {}
        for _document_id, passage in all_passages:
            for term in query_terms & _terms(passage.text):
                frequencies[term] = frequencies.get(term, 0) + 1
        passage_count = max(1, len(all_passages))

        for document_id, passage in all_passages:
            passage_terms = _terms(passage.text)
            overlap = query_terms & passage_terms
            normalized_passage = " ".join(_normalize(passage.text).split())
            entity_hits = sum(bool(pattern.search(normalized_passage)) for pattern in entity_patterns)
            if not overlap and not entity_hits:
                continue
            lexical_score = sum(math.log(1 + passage_count / (1 + frequencies[term]))
                                for term in overlap)
            lexical_score += 2.0 * entity_hits
            if normalized_question in _normalize(passage.text):
                lexical_score += 1.0
            key = (document_id, passage.page_number, passage.chunk_index, passage.content_hash)
            old = candidates.get(key)
            candidates[key] = (passage.text, old[1] if old else 0.0,
                               max(lexical_score, old[2] if old else 0.0))

        results = []
        for (document_id, page_number, _chunk, _hash), (text, vector_score, lexical_score) in candidates.items():
            row = documents[document_id]
            name = row.get("display_name")
            if not name:
                page_paths = row.get("digitized_page_paths") or []
                source = Path(row.get("source_path") or (page_paths[0] if page_paths else document_id))
                name = source.parent.name or source.stem
            results.append(SearchResult(document_id, str(name), page_number, text,
                                        vector_score + lexical_score))
        results.sort(key=lambda item: (-item.score, item.document_name.casefold(), item.page_number))
        page = max(0, page)
        page_size = max(1, page_size)
        start = page * page_size
        return SearchPage(results[start:start + page_size], len(results), page, page_size, extracted)


def answer_library_question(question: str, citations: Sequence[SearchResult],
                            client: OllamaClient | None = None) -> GroundedAnswer:
    if not citations:
        return GroundedAnswer("Chưa tìm thấy tài liệu có căn cứ phù hợp để trả lời câu hỏi này.", [],
                              getattr(client, "model", ""), 0)
    context_parts = []
    included: list[SearchResult] = []
    used = 0
    for citation in citations:
        excerpt = (f"[Tài liệu: {citation.document_name}; mã: {citation.document_id}; "
                   f"trang {citation.page_number}]\n{citation.snippet}")
        cost = len(excerpt.encode("utf-8")) + 2
        if used + cost > MAX_DOCUMENT_CONTEXT_BYTES:
            continue
        used += cost
        context_parts.append(excerpt)
        included.append(citation)
    if not included:
        return GroundedAnswer("Chưa tìm thấy tài liệu có căn cứ phù hợp để trả lời câu hỏi này.", [],
                              getattr(client, "model", ""), 0)
    model = client or OllamaClient()
    answer = model.chat([
        {"role": "system", "content": f"{LIBRARY_ANSWER_SYSTEM_PROMPT}\n<NGUON>\n" +
         "\n\n".join(context_parts) + "\n</NGUON>"},
        {"role": "user", "content": question},
    ], num_ctx=32768)
    if not answer.strip():
        raise ValueError("Model trả về nội dung trống. Vui lòng thử lại.")
    return GroundedAnswer(answer, included, model.model, used)
