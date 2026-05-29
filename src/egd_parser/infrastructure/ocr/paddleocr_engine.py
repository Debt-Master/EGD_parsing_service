import os
from pathlib import Path
from threading import Lock

from egd_parser.application.errors import ParserError
from egd_parser.domain.models.ocr import OCRPageResult, OCRWord
from egd_parser.domain.models.page import PageImage
from egd_parser.domain.ports.ocr_engine import OCREngine
from egd_parser.domain.value_objects.bbox import BoundingBox
from egd_parser.utils.text import normalize_whitespace


class PaddleOCREngine(OCREngine):
    _inference_lock = Lock()

    def __init__(
        self,
        *,
        language: str = "ru",
        use_angle_cls: bool = True,
        base_dir: str | None = None,
        det_model_name: str | None = None,
        rec_model_name: str | None = None,
        textline_orientation_model_name: str | None = None,
        det_model_dir: str | None = None,
        rec_model_dir: str | None = None,
        textline_orientation_model_dir: str | None = None,
        pdx_cache_home: str | None = None,
    ) -> None:
        self._reader = None
        self._reader_lock = Lock()
        self.language = language
        self.use_angle_cls = use_angle_cls
        self.base_dir = base_dir
        self.det_model_name = det_model_name
        self.rec_model_name = rec_model_name
        self.textline_orientation_model_name = textline_orientation_model_name
        self.det_model_dir = det_model_dir
        self.rec_model_dir = rec_model_dir
        self.textline_orientation_model_dir = textline_orientation_model_dir
        self.pdx_cache_home = pdx_cache_home

    def recognize(self, pages: list[PageImage]) -> list[OCRPageResult]:
        reader = self._get_reader()
        results: list[OCRPageResult] = []

        for page in pages:
            if not page.image_path:
                results.append(OCRPageResult(page_number=page.number, text=""))
                continue

            with self._inference_lock:
                raw_result = reader.ocr(page.image_path)
            page_result = raw_result[0] if raw_result else {}
            polygons = page_result.get("dt_polys", [])
            texts = page_result.get("rec_texts", [])
            scores = page_result.get("rec_scores", [])

            words: list[OCRWord] = []
            text_lines: list[tuple[int, int, str]] = []

            for polygon, text_value, score_value in zip(polygons, texts, scores, strict=False):
                if polygon is None:
                    continue

                text = normalize_whitespace(str(text_value))
                confidence = float(score_value)
                if not text:
                    continue

                xs = [point[0] for point in polygon]
                ys = [point[1] for point in polygon]
                bbox = BoundingBox(
                    left=int(min(xs)),
                    top=int(min(ys)),
                    width=int(max(xs) - min(xs)),
                    height=int(max(ys) - min(ys)),
                )
                words.append(
                    OCRWord(
                        text=text,
                        confidence=confidence,
                        bbox=bbox,
                    )
                )
                text_lines.append((bbox.top, bbox.left, text))

            ordered_text = "\n".join(
                entry[2] for entry in sorted(text_lines, key=lambda entry: (entry[0], entry[1]))
            )
            results.append(
                OCRPageResult(
                    page_number=page.number,
                    text=ordered_text,
                    image_path=page.image_path,
                    words=words,
                )
            )

        return results

    def _get_reader(self):
        if self._reader is not None:
            return self._reader

        with self._reader_lock:
            if self._reader is not None:
                return self._reader

            self._reader = self._create_reader()

        return self._reader

    def _create_reader(self):
        if self.base_dir:
            model_base_dir = Path(self.base_dir)
            model_base_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault(
                "PADDLE_PDX_CACHE_HOME",
                self.pdx_cache_home or str(model_base_dir / "pdx-cache"),
            )
            os.environ.setdefault("PADDLE_OCR_BASE_DIR", str(model_base_dir / "models"))
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise ParserError(
                "OCR_ENGINE_UNAVAILABLE",
                "PaddleOCR is not installed.",
                status_code=503,
            ) from exc

        kwargs = {
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": self.use_angle_cls,
            "lang": self.language,
            "text_detection_model_name": self.det_model_name,
            "text_recognition_model_name": self.rec_model_name,
            "text_detection_model_dir": self.det_model_dir,
            "text_recognition_model_dir": self.rec_model_dir,
        }
        if self.use_angle_cls and self.textline_orientation_model_dir:
            kwargs["textline_orientation_model_name"] = self.textline_orientation_model_name
            kwargs["textline_orientation_model_dir"] = self.textline_orientation_model_dir

        try:
            return PaddleOCR(**kwargs)
        except Exception as exc:  # noqa: BLE001
            raise ParserError(
                "OCR_INIT_FAILED",
                "PaddleOCR failed to initialize.",
                status_code=503,
                details={"error": str(exc)[:1000]},
            ) from exc
