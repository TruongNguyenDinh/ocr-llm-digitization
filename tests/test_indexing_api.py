import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.indexing import router


class IndexingApiTests(unittest.TestCase):
    def test_index_status_reports_finalized_counts(self):
        app = FastAPI()
        app.include_router(router)
        with patch("backend.api.indexing._get_status", return_value={"indexed": 4, "pending": 2, "failed": 1}):
            response = TestClient(app).get("/api/library/index-status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"indexed": 4, "pending": 2, "failed": 1})

    def test_reindex_schedules_background_work(self):
        app = FastAPI()
        app.include_router(router)
        with patch("backend.api.indexing._schedule_backfill", return_value="job-123") as schedule:
            response = TestClient(app).post("/api/library/reindex?rebuild=true")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"job_id": "job-123", "status": "queued", "rebuild": True})
        schedule.assert_called_once_with(True)


if __name__ == "__main__":
    unittest.main()
