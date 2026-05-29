from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

from egd_parser.domain.models.page import PageImage
from egd_parser.infrastructure.ocr.paddleocr_engine import PaddleOCREngine


class BlockingReader:
    def __init__(self) -> None:
        self._lock = Lock()
        self.active_calls = 0
        self.max_active_calls = 0

    def ocr(self, image_path: str):
        del image_path
        with self._lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        sleep(0.02)
        with self._lock:
            self.active_calls -= 1
        return [{"dt_polys": [], "rec_texts": [], "rec_scores": []}]


def test_paddleocr_engine_serializes_shared_reader_inference(monkeypatch) -> None:
    reader = BlockingReader()
    engine = PaddleOCREngine()
    monkeypatch.setattr(engine, "_get_reader", lambda: reader)

    pages = [PageImage(number=1, image_path="/tmp/page.png")]

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(engine.recognize, pages) for _ in range(2)]
        for future in futures:
            future.result()

    assert reader.max_active_calls == 1


def test_paddleocr_engine_initializes_reader_once_under_concurrency(monkeypatch) -> None:
    reader = BlockingReader()
    engine = PaddleOCREngine()
    create_calls = 0
    create_lock = Lock()

    def create_reader():
        nonlocal create_calls
        sleep(0.02)
        with create_lock:
            create_calls += 1
        return reader

    monkeypatch.setattr(engine, "_create_reader", create_reader)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(engine._get_reader) for _ in range(2)]
        readers = [future.result() for future in futures]

    assert readers == [reader, reader]
    assert create_calls == 1
