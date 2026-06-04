from __future__ import annotations

from egd_parser.domain.models.ocr import OCRPageResult
from egd_parser.domain.models.page import PageImage
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

    monkeypatch.setattr(runner_module, "extract_page1", lambda results: {"page_1": {}})
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
