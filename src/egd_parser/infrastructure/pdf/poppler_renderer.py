import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from egd_parser.application.errors import ParserError
from egd_parser.domain.models.page import PageImage
from egd_parser.domain.ports.pdf_renderer import PDFRenderer
from egd_parser.infrastructure.settings import get_settings
from egd_parser.utils.image import ensure_directory


class PopplerPDFRenderer(PDFRenderer):
    def render(self, filename: str, content: bytes) -> list[PageImage]:
        settings = get_settings()
        work_dir = Path(tempfile.mkdtemp(prefix="egd_pdf_"))
        pdf_path = work_dir / filename
        pdf_path.write_bytes(content)

        output_prefix = work_dir / "page"
        try:
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-r",
                    str(settings.pdf_render_dpi),
                    str(pdf_path),
                    str(output_prefix),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ParserError(
                "PDF_RENDERER_UNAVAILABLE",
                "pdftoppm is not installed or is not available in PATH.",
                status_code=503,
                details={"filename": filename},
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ParserError(
                "PDF_RENDER_FAILED",
                "PDF renderer failed to convert the document to page images.",
                status_code=422,
                details={
                    "filename": filename,
                    "exit_code": exc.returncode,
                    "stderr": (exc.stderr or "").strip()[:1000],
                },
            ) from exc

        pages: list[PageImage] = []
        rendered_files = sorted(work_dir.glob("page-*.png"))
        if not rendered_files:
            raise ParserError(
                "PDF_RENDER_EMPTY",
                "PDF renderer produced no page images.",
                status_code=422,
                details={"filename": filename},
            )
        cache_dir = ensure_directory(Path("tmp/rendered_pages"))

        for index, rendered_file in enumerate(rendered_files, start=1):
            final_path = cache_dir / f"{pdf_path.stem}-page-{index}.png"
            shutil.copyfile(rendered_file, final_path)
            with Image.open(final_path) as image:
                width, height = image.size
            pages.append(
                PageImage(
                    number=index,
                    width=width,
                    height=height,
                    image_path=str(final_path),
                    source_pdf=str(pdf_path),
                )
            )

        return pages
