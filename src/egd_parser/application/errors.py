from __future__ import annotations


class ParserError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 500,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict:
        payload = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class UnsupportedDocumentError(ParserError):
    def __init__(self, filename: str, content_type: str | None = None) -> None:
        super().__init__(
            "UNSUPPORTED_DOCUMENT_TYPE",
            "Only PDF files are supported by the EGD parser.",
            status_code=415,
            details={
                "filename": filename,
                "content_type": content_type,
            },
        )


class EmptyDocumentError(ParserError):
    def __init__(self, filename: str) -> None:
        super().__init__(
            "EMPTY_DOCUMENT",
            "Uploaded document is empty.",
            status_code=400,
            details={"filename": filename},
        )
