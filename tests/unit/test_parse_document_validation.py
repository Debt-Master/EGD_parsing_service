import pytest

from egd_parser.application.errors import EmptyDocumentError, UnsupportedDocumentError
from egd_parser.application.services.parse_document import ParseDocumentService


def test_parse_document_rejects_non_pdf() -> None:
    service = ParseDocumentService()

    with pytest.raises(UnsupportedDocumentError) as exc_info:
        service.run("sample.rtf", b"{\\rtf1}", content_type="application/rtf")

    assert exc_info.value.code == "UNSUPPORTED_DOCUMENT_TYPE"
    assert exc_info.value.status_code == 415
    assert exc_info.value.details["filename"] == "sample.rtf"


def test_parse_document_rejects_empty_file() -> None:
    service = ParseDocumentService()

    with pytest.raises(EmptyDocumentError) as exc_info:
        service.run("sample.pdf", b"", content_type="application/pdf")

    assert exc_info.value.code == "EMPTY_DOCUMENT"
    assert exc_info.value.status_code == 400
