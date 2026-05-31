import os
from pathlib import Path
from threading import Lock
from time import sleep

from egd_parser.application.errors import ParserError
from egd_parser.domain.models.ocr import OCRPageResult, OCRWord
from egd_parser.domain.models.page import PageImage
from egd_parser.domain.ports.ocr_engine import OCREngine
from egd_parser.domain.value_objects.bbox import BoundingBox
from egd_parser.utils.text import normalize_whitespace


class PaddleOCREngine(OCREngine):
    _inference_lock = Lock()
    _reader_lock = Lock()
    _shared_readers: dict[tuple[object, ...], object] = {}

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
        self._reader_key = (
            self.language,
            self.use_angle_cls,
            self.base_dir,
            self.det_model_name,
            self.rec_model_name,
            self.textline_orientation_model_name,
            self.det_model_dir,
            self.rec_model_dir,
            self.textline_orientation_model_dir,
            self.pdx_cache_home,
        )

    def recognize(self, pages: list[PageImage]) -> list[OCRPageResult]:
        results: list[OCRPageResult] = []

        for page in pages:
            if not page.image_path:
                results.append(OCRPageResult(page_number=page.number, text=""))
                continue

            raw_result = self._run_ocr_with_recovery(page.image_path)
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

    def _run_ocr_with_recovery(self, image_path: str):
        reader = self._get_reader()
        try:
            return self._run_reader_ocr(reader, image_path)
        except ParserError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._invalidate_reader(reader)
            sleep(0.2)
            recovered_reader = self._get_reader()
            try:
                return self._run_reader_ocr(recovered_reader, image_path)
            except ParserError:
                raise
            except Exception as retry_exc:  # noqa: BLE001
                self._invalidate_reader(recovered_reader)
                raise ParserError(
                    "OCR_INFERENCE_FAILED",
                    "PaddleOCR failed during inference.",
                    status_code=503,
                    details={
                        "error": str(retry_exc)[:1000],
                        "previous_error": str(exc)[:1000],
                    },
                ) from retry_exc

    def _run_reader_ocr(self, reader, image_path: str):
        with self._inference_lock:
            return reader.ocr(image_path)

    def _invalidate_reader(self, reader) -> None:
        with self._reader_lock:
            current_reader = self._shared_readers.get(self._reader_key)
            if current_reader is reader:
                self._shared_readers.pop(self._reader_key, None)

    def _get_reader(self):
        reader = self._shared_readers.get(self._reader_key)
        if reader is not None:
            return reader

        with self._reader_lock:
            reader = self._shared_readers.get(self._reader_key)
            if reader is not None:
                return reader

            reader = self._create_reader_with_retries()
            self._shared_readers[self._reader_key] = reader

        return reader

    def _create_reader_with_retries(self):
        attempts = 3
        last_error: ParserError | None = None
        for attempt in range(1, attempts + 1):
            try:
                return self._create_reader()
            except ParserError as exc:
                last_error = exc
                if exc.code != "OCR_INIT_FAILED" or attempt == attempts:
                    break
                sleep(0.5 * attempt)

        if last_error is not None:
            raise last_error

        raise ParserError(
            "OCR_INIT_FAILED",
            "PaddleOCR failed to initialize.",
            status_code=503,
        )

    def _create_reader(self):
        if self.base_dir:
            model_base_dir = Path(self.base_dir)
            model_base_dir.mkdir(parents=True, exist_ok=True)
            os.environ.setdefault(
                "PADDLE_PDX_CACHE_HOME",
                self.pdx_cache_home or str(model_base_dir / "pdx-cache"),
            )
            os.environ.setdefault("PADDLE_OCR_BASE_DIR", str(model_base_dir))
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        self._validate_model_dirs()

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

    def _validate_model_dirs(self) -> None:
        required_dirs = {
            "text_detection_model_dir": self.det_model_dir,
            "text_recognition_model_dir": self.rec_model_dir,
        }
        if self.use_angle_cls:
            required_dirs["textline_orientation_model_dir"] = self.textline_orientation_model_dir

        missing: dict[str, dict[str, object]] = {}
        for name, raw_dir in required_dirs.items():
            if raw_dir is None:
                missing[name] = {"path": None, "missing_files": ["model_dir"]}
                continue

            model_dir = Path(raw_dir)
            required_files = ("inference.json", "inference.yml", "inference.pdiparams")
            missing_files = [
                filename for filename in required_files if not (model_dir / filename).is_file()
            ]
            if not model_dir.is_dir() or missing_files:
                missing[name] = {
                    "path": str(model_dir),
                    "exists": model_dir.is_dir(),
                    "missing_files": missing_files,
                }

        if missing:
            raise ParserError(
                "OCR_MODELS_UNAVAILABLE",
                "PaddleOCR model files are unavailable.",
                status_code=503,
                details={"models": missing},
            )
