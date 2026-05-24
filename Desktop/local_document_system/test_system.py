import os
import sqlite3
import json
import unittest
from unittest.mock import patch, AsyncMock, MagicMock
import tempfile
import asyncio

# Import code modules from the local directory
from parser import extract_text_by_pages
from indexer import chunk_document, get_db_connection, extract_ai_metadata
from search import get_document_metadata, hybrid_search

class TestDocumentSystem(unittest.TestCase):
    
    def setUp(self):
        # Create a temp directory for test database and files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_document_metadata.db")
        
        # Override database connections for tests to use a temp db file
        self.original_get_db_conn = get_db_connection
        import indexer, search, main
        
        def temp_db_conn():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
            
        indexer.get_db_connection = temp_db_conn
        search.get_db_connection = temp_db_conn
        main.get_db_connection = temp_db_conn
        
        # Initialize SQLite schema
        conn = temp_db_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                page_count INTEGER NOT NULL,
                summary TEXT,
                tags TEXT,
                key_findings TEXT,
                entities TEXT,
                status TEXT DEFAULT 'processing',
                error_message TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                id UNINDEXED,
                filename,
                text,
                tags,
                summary
            )
            """
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        # Clean up database overrides
        import indexer, search, main
        indexer.get_db_connection = self.original_get_db_conn
        search.get_db_connection = self.original_get_db_conn
        main.get_db_connection = self.original_get_db_conn
        self.temp_dir.cleanup()

    def test_text_parsing(self):
        """Tests that text parsing extracts lines by mock page blocks"""
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w+", delete=False) as f:
            f.write("Line one content.\n" * 50)  # Write enough to exceed char limit of 2000
            temp_name = f.name
            
        try:
            pages = extract_text_by_pages(temp_name)
            self.assertTrue(len(pages) >= 1)
            self.assertEqual(pages[0]["page"], 1)
            self.assertIn("Line one content.", pages[0]["text"])
        finally:
            os.remove(temp_name)

    def test_chunking_logic(self):
        """Tests recursive chunk overlapping rules"""
        pages = [
            {"page": 1, "text": "A" * 1200},  # Shard should break into 2 overlapping chunks
            {"page": 2, "text": "B" * 500}
        ]
        
        chunks = chunk_document(pages, chunk_size=1000, chunk_overlap=200)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0]["page"], 1)
        self.assertEqual(chunks[2]["page"], 2)

    @patch("indexer.httpx.AsyncClient")
    def test_ollama_metadata_extraction(self, mock_client):
        """Tests local Ollama metadata parser logic with mock response"""
        # Mock response object
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": json.dumps({
                "summary": "This is a test summary description.",
                "tags": ["Finance", "Audit"],
                "key_findings": ["First finding.", "Second finding."],
                "entities": {
                    "Companies": ["Test Corp"],
                    "Dates": ["2026-05-23"],
                    "Project_Names": ["Scope Sync"]
                }
            })
        }
        
        # Configure client mock to return response on post
        client_instance = AsyncMock()
        client_instance.post.return_value = mock_response
        mock_client.return_value.__aenter__.return_value = client_instance
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        meta = loop.run_until_complete(extract_ai_metadata("Sample text..."))
        
        self.assertEqual(meta["summary"], "This is a test summary description.")
        self.assertIn("Finance", meta["tags"])
        self.assertEqual(meta["entities"]["Companies"][0], "Test Corp")

    def test_database_metadata_retrieval(self):
        """Tests loading document statistics and profiles from SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO documents (id, filename, file_size_bytes, page_count, summary, tags, key_findings, entities, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "doc-test-123",
                "test_sheet.pdf",
                50000,
                3,
                "Summary description of test sheet.",
                json.dumps(["Spreadsheet", "Data"]),
                json.dumps(["Finding A", "Finding B"]),
                json.dumps({"Companies": ["Company X"], "Dates": ["2026"], "Project_Names": []}),
                "completed"
            )
        )
        conn.commit()
        conn.close()
        
        meta = get_document_metadata("doc-test-123")
        self.assertIsNotNone(meta)
        self.assertEqual(meta["filename"], "test_sheet.pdf")
        self.assertIn("Spreadsheet", meta["tags"])
        self.assertEqual(meta["entities"]["Companies"][0], "Company X")

if __name__ == "__main__":
    unittest.main()
