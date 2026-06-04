from __future__ import annotations

from threading import Event, Lock, get_ident
from time import monotonic, sleep

from egd_parser.api.schemas.response import ParseResponse
from egd_parser.application.services.job_models import UploadedDocument
from egd_parser.application.services.job_service import InMemoryJobStore, JobService


class BlockingJobService(JobService):
    def __init__(self) -> None:
        super().__init__(store=InMemoryJobStore(), max_workers=1, max_active_jobs=1)
        self.first_started = Event()
        self.release_first = Event()
        self._lock = Lock()
        self.active_parses = 0
        self.max_active_parses = 0

    def _parse_document(self, file: UploadedDocument) -> ParseResponse:
        with self._lock:
            self.active_parses += 1
            self.max_active_parses = max(self.max_active_parses, self.active_parses)

        try:
            if file.filename == "first.pdf":
                self.first_started.set()
                assert self.release_first.wait(timeout=2.0)
            return ParseResponse(filename=file.filename, pages=1, extracted_data={})
        finally:
            with self._lock:
                self.active_parses -= 1

    def _send_callback(self, job_id: str) -> None:
        del job_id


def wait_for_status(service: JobService, job_id: str, status: str, timeout: float = 2.0) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        record = service.store.get(job_id)
        if record is not None and record.status == status:
            return
        sleep(0.01)
    record = service.store.get(job_id)
    actual = record.status if record is not None else None
    raise AssertionError(f"Expected job {job_id} status {status}, got {actual}")


def test_job_service_limits_active_jobs() -> None:
    service = BlockingJobService()
    first = UploadedDocument(filename="first.pdf", content=b"%PDF-1.3", content_type="application/pdf")
    second = UploadedDocument(filename="second.pdf", content=b"%PDF-1.3", content_type="application/pdf")

    first_status = service.enqueue_job([first])
    assert service.first_started.wait(timeout=2.0)

    second_status = service.enqueue_job([second])
    sleep(0.05)

    assert service.store.get(first_status.job_id).status == "running"
    assert service.store.get(second_status.job_id).status == "queued"
    assert service.max_active_parses == 1

    service.release_first.set()
    wait_for_status(service, first_status.job_id, "completed")
    wait_for_status(service, second_status.job_id, "completed")
    assert service.max_active_parses == 1
    assert service.get_metrics()["max_active_jobs"] == 1
    service.shutdown()


class WarmupRecordingParseService:
    def __init__(self) -> None:
        self.thread_ids: list[int] = []

    def warmup(self) -> None:
        self.thread_ids.append(get_ident())

    def run(self, filename: str, content: bytes, content_type: str | None = None) -> ParseResponse:
        del content, content_type
        self.thread_ids.append(get_ident())
        return ParseResponse(filename=filename, pages=1, extracted_data={})


class WarmupRecordingJobService(JobService):
    def __init__(self, parse_service: WarmupRecordingParseService) -> None:
        self.recording_parse_service = parse_service
        super().__init__(store=InMemoryJobStore(), max_workers=1, max_active_jobs=1)

    def _get_parse_service(self):
        return self.recording_parse_service

    def _send_callback(self, job_id: str) -> None:
        del job_id


def test_job_service_warmup_and_parse_run_on_same_worker_thread() -> None:
    parse_service = WarmupRecordingParseService()
    service = WarmupRecordingJobService(parse_service)
    document = UploadedDocument(filename="sample.pdf", content=b"%PDF-1.3", content_type="application/pdf")

    service.warmup(timeout=2.0)
    status = service.enqueue_job([document])
    wait_for_status(service, status.job_id, "completed")

    assert len(parse_service.thread_ids) == 2
    assert parse_service.thread_ids[0] == parse_service.thread_ids[1]
    assert parse_service.thread_ids[0] != get_ident()
    service.shutdown()
