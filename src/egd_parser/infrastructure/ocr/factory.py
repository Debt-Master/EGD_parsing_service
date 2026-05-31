from pathlib import Path

from egd_parser.domain.ports.ocr_engine import OCREngine
from egd_parser.infrastructure.ocr.easyocr_engine import EasyOCREngine
from egd_parser.infrastructure.ocr.mock_engine import MockOCREngine
from egd_parser.infrastructure.ocr.paddleocr_engine import PaddleOCREngine
from egd_parser.infrastructure.ocr.tesseract_engine import TesseractOCREngine
from egd_parser.infrastructure.settings import Settings


def create_ocr_engine(settings: Settings) -> OCREngine:
    if settings.ocr_engine == "paddleocr":
        det_model_dir = resolve_model_dir(settings.paddleocr_det_model_dir)
        rec_model_dir = resolve_model_dir(settings.paddleocr_rec_model_dir)
        textline_orientation_model_dir = resolve_model_dir(
            settings.paddleocr_textline_orientation_model_dir
        )
        model_base_dir = common_model_base_dir(det_model_dir, rec_model_dir)
        return PaddleOCREngine(
            language=settings.paddleocr_language,
            use_angle_cls=settings.paddleocr_use_angle_cls,
            base_dir=str(model_base_dir or settings.paddleocr_base_dir),
            det_model_name=settings.paddleocr_det_model_name,
            rec_model_name=settings.paddleocr_rec_model_name,
            textline_orientation_model_name=settings.paddleocr_textline_orientation_model_name,
            det_model_dir=str(det_model_dir),
            rec_model_dir=str(rec_model_dir),
            textline_orientation_model_dir=str(textline_orientation_model_dir),
            pdx_cache_home=str(settings.paddle_pdx_cache_home),
        )
    if settings.ocr_engine == "easyocr":
        return EasyOCREngine()
    if settings.ocr_engine == "tesseract":
        return TesseractOCREngine()
    if settings.ocr_engine == "mock":
        return MockOCREngine()
    raise ValueError(f"Unsupported OCR engine: {settings.ocr_engine}")


def resolve_model_dir(configured_dir: Path) -> Path:
    if is_paddle_model_dir(configured_dir):
        return configured_dir

    project_root = Path(__file__).resolve().parents[4]
    for candidate in (
        project_root / "models" / configured_dir.name,
        Path("/app/models") / configured_dir.name,
    ):
        if is_paddle_model_dir(candidate):
            return candidate

    return configured_dir


def is_paddle_model_dir(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "inference.json").is_file()
        and (path / "inference.yml").is_file()
        and (path / "inference.pdiparams").is_file()
    )


def common_model_base_dir(*model_dirs: Path) -> Path | None:
    parents = {path.parent for path in model_dirs if is_paddle_model_dir(path)}
    if len(parents) == 1:
        return parents.pop()
    return None
