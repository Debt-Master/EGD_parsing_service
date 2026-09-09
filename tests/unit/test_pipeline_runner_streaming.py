from __future__ import annotations

import pytest

from egd_parser.application.errors import PropertyAddressNotInReferenceError
from egd_parser.domain.models.ocr import OCRPageResult
from egd_parser.domain.models.page import PageImage
from egd_parser.domain.reference.buildings import ManagedBuilding
from egd_parser.pipeline import runner as runner_module
from egd_parser.pipeline.runner import PipelineRunner


class StreamingRenderer:
    def __init__(self) -> None:
        self.render_called = False

    def render(self, filename: str, content: bytes) -> list[PageImage]:
        del filename, content
        self.render_called = True
        return []

    def render_iter(self, filename: str, content: bytes):
        del filename, content
        yield PageImage(number=1, image_path="/tmp/page-1.png")
        yield PageImage(number=2, image_path="/tmp/page-2.png")


class RecordingOCR:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def recognize(self, pages: list[PageImage]) -> list[OCRPageResult]:
        self.batch_sizes.append(len(pages))
        return [
            OCRPageResult(
                page_number=page.number,
                text=f"page {page.number}",
                image_path=page.image_path,
            )
            for page in pages
        ]


def test_pipeline_runner_ocr_pages_sequentially(monkeypatch) -> None:
    renderer = StreamingRenderer()
    ocr = RecordingOCR()
    settings = type("Settings", (), {"ocr_engine": "mock"})()
    pipeline = PipelineRunner.__new__(PipelineRunner)
    pipeline.settings = settings
    pipeline.renderer = renderer
    pipeline.ocr = ocr

    monkeypatch.setattr(
        runner_module,
        "extract_page1",
        lambda results, managed_buildings=None: {"page_1": {}},
    )
    monkeypatch.setattr(
        runner_module,
        "extract_page2",
        lambda results: {"registered_persons_constantly": {"persons": []}},
    )
    monkeypatch.setattr(
        runner_module,
        "apply_row_reocr_fallback",
        lambda persons_block, pages, ocr_engine: persons_block,
    )

    document = pipeline.run(filename="sample.pdf", content=b"%PDF-1.3")

    assert not renderer.render_called
    assert ocr.batch_sizes == [1, 1]
    assert document.page_count == 2
    assert document.metadata["page_images"] == ["/tmp/page-1.png", "/tmp/page-2.png"]


def test_pipeline_stops_before_import_callback_when_address_is_not_in_db_realty(
    monkeypatch,
) -> None:
    pipeline = PipelineRunner.__new__(PipelineRunner)
    pipeline.settings = type("Settings", (), {"ocr_engine": "mock"})()
    pipeline.renderer = StreamingRenderer()
    pipeline.ocr = RecordingOCR()
    monkeypatch.setattr(
        runner_module,
        "extract_page1",
        lambda results, managed_buildings=None: {
            "page_1": {
                "property_address": {
                    "raw": "ул. Неизвестная, дом 1, кв. 2",
                    "street": "ул. Неизвестная",
                    "house": "1",
                    "apartment": "2",
                    "__reference__": {"mode": "db_realty", "matched": False},
                }
            }
        },
    )
    reference = [
        ManagedBuilding("", "Донецкая", "1", None, "", "")
    ]

    with pytest.raises(PropertyAddressNotInReferenceError) as caught:
        pipeline.run("sample.pdf", b"%PDF-1.3", reference)

    assert caught.value.code == "PROPERTY_ADDRESS_NOT_IN_REFERENCE"
    assert "Неизвестная" in caught.value.message
