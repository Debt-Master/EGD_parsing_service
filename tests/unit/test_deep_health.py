from pathlib import Path
from types import SimpleNamespace

from egd_parser.api.routes import health
from egd_parser.infrastructure.settings import get_settings


class _FakeJobService:
    def __init__(self) -> None:
        self.warmed_up = False

    def warmup(self, timeout=None):
        assert timeout == 60.0
        self.warmed_up = True


def test_read_meminfo(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "\n".join(
            [
                "MemTotal:        1024 kB",
                "MemAvailable:    512 kB",
                "SwapTotal:       256 kB",
                "SwapFree:        128 kB",
            ]
        ),
        encoding="utf-8",
    )

    assert health.read_meminfo(meminfo) == {
        "mem_total_kb": 1024,
        "mem_available_kb": 512,
        "swap_total_kb": 256,
        "swap_free_kb": 128,
    }


def test_deep_healthcheck_initializes_ocr(monkeypatch) -> None:
    settings = get_settings()
    job_service = _FakeJobService()
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings, job_service=job_service))
    )

    monkeypatch.setattr(health.shutil, "which", lambda command: "/usr/bin/pdftoppm")

    response = health.deep_healthcheck(request)

    assert response.status_code == 200
    assert job_service.warmed_up is True
