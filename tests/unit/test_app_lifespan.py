from __future__ import annotations

import asyncio
from types import SimpleNamespace

from egd_parser.api import app as app_module
from egd_parser.infrastructure.settings import Settings


class FakeEngine:
    def __init__(self) -> None:
        self.warmed_up = False

    def warmup(self) -> None:
        self.warmed_up = True


def test_lifespan_preloads_ocr_with_warmup(monkeypatch, tmp_path) -> None:
    settings = Settings(
        ocr_preload=True,
        jobs_db_path=tmp_path / "storage" / "jobs.sqlite3",
        uploads_dir=tmp_path / "uploads",
        rendered_pages_dir=tmp_path / "rendered_pages",
    )
    engine = FakeEngine()

    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module, "create_ocr_engine", lambda received_settings: engine)

    async def run_lifespan() -> None:
        async with app_module.lifespan(SimpleNamespace()):
            assert engine.warmed_up is True

    asyncio.run(run_lifespan())
