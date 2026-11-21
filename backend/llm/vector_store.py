"""Persistent local Qdrant index for finalized document passages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models


@dataclass(frozen=True)
class Passage:
    page_number: int
    chunk_index: int
    text: str
    content_hash: str


@dataclass(frozen=True)
class ScoredPassage:
    document_id: str
    page_number: int
    chunk_index: int
    text: str
    content_hash: str
    score: float


class LocalPassageIndex:
    def __init__(self, path: str | Path = "storage/vector_index", *, vector_size: int = 768,
                 collection_name: str = "document_passages") -> None:
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.path = str(path)
        self.client = QdrantClient(path=str(path))
        if not self.client.collection_exists(collection_name):
            self.client.create_collection(collection_name, vectors_config=models.VectorParams(
                size=vector_size, distance=models.Distance.COSINE))

    @staticmethod
    def _point_id(document_id: str, passage: Passage) -> str:
        identity = f"{document_id}:{passage.page_number}:{passage.chunk_index}:{passage.content_hash}"
        return str(uuid5(NAMESPACE_URL, identity))

    def upsert_document(self, document_id: str, passages: list[tuple[Passage, list[float]]]) -> None:
        self.client.delete(self.collection_name, points_selector=models.FilterSelector(
            filter=models.Filter(must=[models.FieldCondition(
                key="document_id", match=models.MatchValue(value=document_id))])), wait=True)
        if passages:
            points = [models.PointStruct(
                id=self._point_id(document_id, passage), vector=vector,
                payload={"document_id": document_id, "page_number": passage.page_number,
                         "chunk_index": passage.chunk_index, "text": passage.text,
                         "content_hash": passage.content_hash},
            ) for passage, vector in passages]
            self.client.upsert(self.collection_name, points, wait=True)

    def search(self, vector: list[float], *, document_id: str | None = None,
               limit: int = 20, offset: int = 0,
               score_threshold: float | None = None) -> list[ScoredPassage]:
        query_filter = None
        if document_id is not None:
            query_filter = models.Filter(must=[models.FieldCondition(
                key="document_id", match=models.MatchValue(value=document_id))])
        result = self.client.query_points(self.collection_name, query=vector, query_filter=query_filter,
                                          limit=max(1, limit), offset=max(0, offset), with_payload=True,
                                          score_threshold=score_threshold)
        return [ScoredPassage(
            document_id=str(point.payload["document_id"]),
            page_number=int(point.payload["page_number"]),
            chunk_index=int(point.payload["chunk_index"]), text=str(point.payload["text"]),
            content_hash=str(point.payload["content_hash"]), score=float(point.score),
        ) for point in result.points]

    def delete_document(self, document_id: str) -> None:
        self.client.delete(self.collection_name, points_selector=models.FilterSelector(
            filter=models.Filter(must=[models.FieldCondition(
                key="document_id", match=models.MatchValue(value=document_id))])), wait=True)

    def reset(self) -> None:
        self.client.delete_collection(self.collection_name)
        self.client.create_collection(self.collection_name, vectors_config=models.VectorParams(
            size=self.vector_size, distance=models.Distance.COSINE))

    def count(self, document_id: str | None = None) -> int:
        query_filter = None if document_id is None else models.Filter(must=[models.FieldCondition(
            key="document_id", match=models.MatchValue(value=document_id))])
        return int(self.client.count(self.collection_name, count_filter=query_filter, exact=True).count)

    def close(self) -> None:
        self.client.close()
