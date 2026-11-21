"""Global semantic search and answer routes."""

from dataclasses import asdict
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.api.indexing import _get_service
from backend.llm.library_search import LibrarySearchService, answer_library_question
from backend.llm.ollama_client import OllamaClient, OllamaError


router = APIRouter(prefix="/api/library")
logger = logging.getLogger(__name__)


class SearchAIRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    page: int = Field(default=0, ge=0)
    page_size: int = Field(default=20, ge=1)


def run_library_search(question: str, page: int = 0, page_size: int = 20) -> dict[str, object]:
    indexer = _get_service()
    model = OllamaClient()
    searcher = LibrarySearchService(
        indexer.repository, indexer.vector_index, indexer.embedder, model,
        storage_root=indexer.storage_root)
    search_page = searcher.search_library(question, page, page_size)
    grounded = answer_library_question(question, search_page.results, model)
    return {
        "answer": grounded.answer,
        "model": grounded.model,
        "extracted_terms": {
            "terms": search_page.extracted_terms.terms,
            "entities": search_page.extracted_terms.entities,
            "dates": search_page.extracted_terms.dates,
            "identifiers": search_page.extracted_terms.identifiers,
        },
        "citations": [asdict(item) for item in grounded.citations],
        "results": [asdict(item) for item in search_page.results],
        "page": search_page.page,
        "page_size": search_page.page_size,
        "total": search_page.total,
        "context_used_bytes": grounded.context_used_bytes,
        "index_status": indexer.repository.get_index_status(),
    }


@router.post("/search-ai")
def search_ai(request: SearchAIRequest) -> dict[str, object]:
    try:
        return run_library_search(request.question.strip(), request.page, request.page_size)
    except OllamaError as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.exception("Global document search failed")
        raise HTTPException(503, "Không thể tìm kiếm thư viện lúc này.") from exc
