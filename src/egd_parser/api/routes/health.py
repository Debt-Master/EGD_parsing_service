import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from egd_parser.application.errors import ParserError
from egd_parser.infrastructure.ocr.factory import create_ocr_engine

router = APIRouter(tags=["health"])


@router.get("/health")
def healthcheck(request: Request) -> dict:
    settings = request.app.state.settings
    return build_health_payload(settings)


@router.get("/health/deep")
def deep_healthcheck(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    started_at = time.perf_counter()
    payload = build_health_payload(settings)
    payload["status"] = "ok"
    payload["checks"] = {
        "pdftoppm": {
            "status": "ok" if payload["pdftoppm_available"] else "failed",
            "available": payload["pdftoppm_available"],
        },
        "ocr_init": {
            "status": "pending",
            "engine": settings.ocr_engine,
        },
    }

    try:
        engine = create_ocr_engine(settings)
        engine.recognize([])
        payload["checks"]["ocr_init"] = {
            "status": "ok",
            "engine": settings.ocr_engine,
        }
    except ParserError as exc:
        payload["status"] = "failed"
        payload["checks"]["ocr_init"] = {
            "status": "failed",
            "engine": settings.ocr_engine,
            "error_code": exc.code,
            "error": exc.message,
            "details": exc.details,
        }
    except Exception as exc:  # noqa: BLE001
        payload["status"] = "failed"
        payload["checks"]["ocr_init"] = {
            "status": "failed",
            "engine": settings.ocr_engine,
            "error_code": "OCR_INIT_FAILED",
            "error": str(exc),
        }

    if not payload["pdftoppm_available"]:
        payload["status"] = "failed"

    payload["duration_ms"] = round((time.perf_counter() - started_at) * 1000, 2)
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)


def build_health_payload(settings) -> dict:
    det_model_dir = settings.paddleocr_det_model_dir
    rec_model_dir = settings.paddleocr_rec_model_dir
    ori_model_dir = settings.paddleocr_textline_orientation_model_dir

    return {
        "status": "ok",
        "app_env": settings.app_env,
        "ocr_engine": settings.ocr_engine,
        "pdftoppm_available": shutil.which("pdftoppm") is not None,
        "storage": {
            "jobs_db_path": str(settings.jobs_db_path),
            "uploads_dir": str(settings.uploads_dir),
            "rendered_pages_dir": str(settings.rendered_pages_dir),
        },
        "memory": read_meminfo(),
        "models": {
            "det_model_dir": str(det_model_dir),
            "det_model_exists": det_model_dir.exists(),
            "rec_model_dir": str(rec_model_dir),
            "rec_model_exists": rec_model_dir.exists(),
            "orientation_model_dir": str(ori_model_dir),
            "orientation_model_exists": ori_model_dir.exists(),
        },
    }


def read_meminfo(path: Path = Path("/proc/meminfo")) -> dict:
    keys = {
        "MemTotal": "mem_total_kb",
        "MemAvailable": "mem_available_kb",
        "SwapTotal": "swap_total_kb",
        "SwapFree": "swap_free_kb",
    }
    values: dict[str, int] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            name, _, raw_value = line.partition(":")
            if name in keys:
                values[keys[name]] = int(raw_value.strip().split()[0])
    except OSError:
        return {}
    return values
