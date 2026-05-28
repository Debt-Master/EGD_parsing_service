from egd_parser.api.schemas.response import ParseResponse
from egd_parser.application.errors import EmptyDocumentError, UnsupportedDocumentError
from egd_parser.domain.models.document import ParsedDocument
from egd_parser.pipeline.runner import PipelineRunner


class ParseDocumentService:
    def __init__(self) -> None:
        self.pipeline: PipelineRunner | None = None

    def run(self, filename: str, content: bytes, content_type: str | None = None) -> ParseResponse:
        self._validate_pdf(filename, content, content_type)
        if self.pipeline is None:
            self.pipeline = PipelineRunner()
        document = self.pipeline.run(filename=filename, content=content)
        return self._to_response(document)

    @staticmethod
    def _validate_pdf(filename: str, content: bytes, content_type: str | None = None) -> None:
        if not content:
            raise EmptyDocumentError(filename)

        normalized_name = filename.lower()
        normalized_type = (content_type or "").lower()
        has_pdf_extension = normalized_name.endswith(".pdf")
        has_pdf_magic = content.startswith(b"%PDF")
        has_pdf_content_type = normalized_type in ("application/pdf", "application/x-pdf")

        if not has_pdf_magic and not (has_pdf_extension and has_pdf_content_type):
            raise UnsupportedDocumentError(filename, content_type)

    @staticmethod
    def _to_response(document: ParsedDocument) -> ParseResponse:
        return ParseResponse(
            filename=document.filename,
            pages=document.page_count,
            warnings=document.warnings,
            extracted_data=document.extracted_data,
            metadata=document.metadata,
        )
