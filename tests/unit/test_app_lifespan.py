from __future__ import annotations

import asyncio
from types import SimpleNamespace

from egd_parser.api import app as app_module
from egd_parser.infrastructure.settings import Settings


class FakeJobService:
    def __init__(self) -> None:
        self.warmed_up = False
        self.shutdown_called = False

    def warmup(self) -> None:
        self.warmed_up = True

    def shutdown(self) -> None:
        self.shutdown_called = True


def test_lifespan_preloads_ocr_with_warmup(monkeypatch, tmp_path) -> None:
    settings = Settings(
        ocr_preload=True,
        jobs_db_path=tmp_path / "storage" / "jobs.sqlite3",
        uploads_dir=tmp_path / "uploads",
        rendered_pages_dir=tmp_path / "rendered_pages",
    )
    job_service = FakeJobService()
    app = SimpleNamespace(state=SimpleNamespace(job_service=job_service))

    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    async def run_lifespan() -> None:
        async with app_module.lifespan(app):
            assert job_service.warmed_up is True
            assert job_service.shutdown_called is False

    asyncio.run(run_lifespan())
    assert job_service.shutdown_called is True
