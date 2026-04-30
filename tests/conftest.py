from __future__ import annotations

import os


os.environ["APP_ENV"] = "test"
os.environ["OCR_ENGINE"] = "mock"
os.environ["JOBS_DB_PATH"] = "/tmp/egd_parser_tests/jobs.sqlite3"
os.environ["UPLOADS_DIR"] = "/tmp/egd_parser_tests/uploads"
os.environ["ATTEMPTS_DIR"] = "/tmp/egd_parser_tests/attempts"
os.environ["RENDERED_PAGES_DIR"] = "/tmp/egd_parser_tests/rendered_pages"
os.environ["PADDLE_PDX_CACHE_HOME"] = "/tmp/egd_parser_tests/pdx-cache"
