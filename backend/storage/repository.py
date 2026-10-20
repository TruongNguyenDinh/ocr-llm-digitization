import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class SQLiteRepository:
    def __init__(self, database_path: str | Path = "storage/metadata.sqlite3") -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    review_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    label_code TEXT NOT NULL,
                    label_name TEXT NOT NULL,
                    sender TEXT,
                    recipient TEXT,
                    date_time TEXT,
                    document_type TEXT NOT NULL,
                    page_count INTEGER NOT NULL,
                    source_path TEXT NOT NULL,
                    digitized_dir TEXT NOT NULL,
                    digitized_page_paths TEXT NOT NULL,
                    origin_pdf_path TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, sequence)
                )
                """
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def next_sequence(connection: sqlite3.Connection, user_id: str) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM documents WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row[0])

    @staticmethod
    def insert_document(connection: sqlite3.Connection, record: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO documents (
                document_id, review_id, user_id, sequence, label_code, label_name,
                sender, recipient, date_time, document_type, page_count, source_path,
                digitized_dir, digitized_page_paths, origin_pdf_path, review_status,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["document_id"],
                record["review_id"],
                record["user_id"],
                record["sequence"],
                record["label_code"],
                record["label_name"],
                record["sender"],
                record["recipient"],
                record["date_time"],
                record["document_type"],
                record["page_count"],
                record["source_path"],
                record["digitized_dir"],
                json.dumps(record["digitized_page_paths"], ensure_ascii=False),
                record["origin_pdf_path"],
                record["review_status"],
                record["created_at"],
            ),
        )

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["digitized_page_paths"] = json.loads(record["digitized_page_paths"])
        return record
