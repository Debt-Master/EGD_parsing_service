from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from egd_parser.api.normalizer import normalize
from egd_parser.api.schemas.response import ParseResponse
from egd_parser.application.errors import ParserError
from egd_parser.application.services.parse_document import ParseDocumentService

router = APIRouter(tags=["parse"])


@router.post("/parse", response_model=ParseResponse)
async def parse_document(file: UploadFile = File(...)) -> ParseResponse:
    content = await file.read()
    service = ParseDocumentService()
    try:
        return service.run(
            filename=file.filename or "document.pdf",
            content=content,
            content_type=file.content_type,
        )
    except ParserError as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_dict()})


@router.post("/parse/normalized")
async def parse_document_normalized(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    service = ParseDocumentService()
    try:
        result = service.run(
            filename=file.filename or "document.pdf",
            content=content,
            content_type=file.content_type,
        )
    except ParserError as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.to_dict()})
    return normalize(result.model_dump())
