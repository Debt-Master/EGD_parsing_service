from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from time import sleep
import logging

import pytest

from egd_parser.application.errors import ParserError
from egd_parser.domain.models.page import PageImage
from egd_parser.infrastructure.ocr.paddleocr_engine import PaddleOCREngine


@pytest.fixture(autouse=True)
def clear_shared_readers():
    PaddleOCREngine._shared_readers.clear()
    yield
    PaddleOCREngine._shared_readers.clear()


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


class FailingReader:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def ocr(self, image_path: str):
        del image_path
        raise self.error


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


def test_paddleocr_engine_uses_thread_local_readers(monkeypatch) -> None:
    engine = PaddleOCREngine()
    create_calls = 0
    create_lock = Lock()

    def create_reader():
        nonlocal create_calls
        sleep(0.02)
        with create_lock:
            create_calls += 1
            reader_number = create_calls
        reader = BlockingReader()
        reader.reader_number = reader_number
        return reader

    monkeypatch.setattr(engine, "_create_reader", create_reader)
    barrier = Barrier(2)

    def get_reader():
        barrier.wait(timeout=1.0)
        return engine._get_reader()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(get_reader) for _ in range(2)]
        readers = [future.result() for future in futures]

    assert readers[0] is not readers[1]
    assert create_calls == 2


def test_paddleocr_engine_warmup_initializes_reader(monkeypatch) -> None:
    reader = BlockingReader()
    engine = PaddleOCREngine()
    create_calls = 0

    def create_reader():
        nonlocal create_calls
        create_calls += 1
        return reader

    monkeypatch.setattr(engine, "_create_reader", create_reader)

    engine.warmup()

    assert engine._get_reader() is reader
    assert create_calls == 1


def test_paddleocr_engine_reuses_reader_across_instances_in_same_thread(monkeypatch) -> None:
    reader = BlockingReader()
    create_calls = 0

    def create_reader(self):
        nonlocal create_calls
        del self
        create_calls += 1
        return reader

    monkeypatch.setattr(PaddleOCREngine, "_create_reader", create_reader)
    engines = [PaddleOCREngine(), PaddleOCREngine()]

    readers = [engine._get_reader() for engine in engines]

    assert readers == [reader, reader]
    assert create_calls == 1


def test_paddleocr_engine_retries_transient_initialization_failure(monkeypatch) -> None:
    reader = BlockingReader()
    engine = PaddleOCREngine()
    create_calls = 0

    def create_reader():
        nonlocal create_calls
        create_calls += 1
        if create_calls == 1:
            raise ParserError("OCR_INIT_FAILED", "PaddleOCR failed to initialize.")
        return reader

    monkeypatch.setattr(engine, "_create_reader", create_reader)
    monkeypatch.setattr("egd_parser.infrastructure.ocr.paddleocr_engine.sleep", lambda delay: None)

    assert engine._get_reader() is reader
    assert create_calls == 2


def test_paddleocr_engine_reports_missing_model_files(tmp_path) -> None:
    det_dir = tmp_path / "missing_det"
    rec_dir = tmp_path / "missing_rec"
    engine = PaddleOCREngine(
        det_model_dir=str(det_dir),
        rec_model_dir=str(rec_dir),
    )

    with pytest.raises(ParserError) as exc_info:
        engine._validate_model_dirs()

    assert exc_info.value.code == "OCR_MODELS_UNAVAILABLE"
    assert exc_info.value.details["models"]["text_detection_model_dir"]["path"] == str(det_dir)
    assert exc_info.value.details["models"]["text_recognition_model_dir"]["path"] == str(rec_dir)


def test_paddleocr_engine_recovers_from_transient_inference_failure(monkeypatch, caplog) -> None:
    failing_reader = FailingReader(RuntimeError("std::exception"))
    recovered_reader = BlockingReader()
    readers = [failing_reader, recovered_reader]
    engine = PaddleOCREngine()

    def create_reader():
        return readers.pop(0)

    monkeypatch.setattr(engine, "_create_reader", create_reader)
    monkeypatch.setattr("egd_parser.infrastructure.ocr.paddleocr_engine.sleep", lambda delay: None)

    caplog.set_level(logging.WARNING)
    results = engine.recognize([PageImage(number=1, image_path="/tmp/page.png")])

    assert len(results) == 1
    assert engine._get_reader() is recovered_reader
    assert "PaddleOCR inference failed for /tmp/page.png; invalidating reader and retrying" in caplog.text
    assert "std::exception" in caplog.text
    assert "/tmp/page.png" in caplog.text


def test_paddleocr_engine_reports_inference_failure_after_retry(monkeypatch) -> None:
    readers = [
        FailingReader(RuntimeError("std::exception")),
        FailingReader(RuntimeError("std::exception again")),
    ]
    engine = PaddleOCREngine()

    def create_reader():
        return readers.pop(0)

    monkeypatch.setattr(engine, "_create_reader", create_reader)
    monkeypatch.setattr("egd_parser.infrastructure.ocr.paddleocr_engine.sleep", lambda delay: None)

    with pytest.raises(ParserError) as exc_info:
        engine.recognize([PageImage(number=1, image_path="/tmp/page.png")])

    assert exc_info.value.code == "OCR_INFERENCE_FAILED"
    assert "std::exception again" in exc_info.value.details["error"]
