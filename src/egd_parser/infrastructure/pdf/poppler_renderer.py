import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

from PIL import Image

from egd_parser.application.errors import ParserError
from egd_parser.domain.models.page import PageImage
from egd_parser.domain.ports.pdf_renderer import PDFRenderer
from egd_parser.infrastructure.settings import get_settings
from egd_parser.utils.image import ensure_directory


class PopplerPDFRenderer(PDFRenderer):
    def render(self, filename: str, content: bytes) -> list[PageImage]:
        return list(self.render_iter(filename=filename, content=content))

    def render_iter(self, filename: str, content: bytes) -> Iterator[PageImage]:
        settings = get_settings()
        work_dir = Path(tempfile.mkdtemp(prefix="egd_pdf_"))
        pdf_path = work_dir / filename
        pdf_path.write_bytes(content)
        cache_dir = ensure_directory(settings.rendered_pages_dir)

        try:
            page_count = self._read_page_count(pdf_path, filename)
            for page_number in range(1, page_count + 1):
                yield self._render_page(
                    pdf_path=pdf_path,
                    filename=filename,
                    work_dir=work_dir,
                    cache_dir=cache_dir,
                    page_number=page_number,
                    dpi=settings.pdf_render_dpi,
                )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

    def _read_page_count(self, pdf_path: Path, filename: str) -> int:
        try:
            result = subprocess.run(
                [
                    "pdfinfo",
                    str(pdf_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ParserError(
                "PDF_RENDERER_UNAVAILABLE",
                "pdfinfo is not installed or is not available in PATH.",
                status_code=503,
                details={"filename": filename},
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise ParserError(
                "PDF_RENDER_FAILED",
                "PDF renderer failed to read document metadata.",
                status_code=422,
                details={
                    "filename": filename,
                    "exit_code": exc.returncode,
                    "stderr": (exc.stderr or "").strip()[:1000],
                },
            ) from exc

        for line in result.stdout.splitlines():
            name, _, value = line.partition(":")
            if name.strip().lower() != "pages":
                continue
            try:
                page_count = int(value.strip())
            except ValueError as exc:
                raise ParserError(
                    "PDF_RENDER_FAILED",
                    "PDF renderer failed to read page count.",
                    status_code=422,
                    details={"filename": filename, "pages": value.strip()},
                ) from exc
            if page_count > 0:
                return page_count
            break

        raise ParserError(
            "PDF_RENDER_EMPTY",
            "PDF renderer found no pages.",
            status_code=422,
            details={"filename": filename},
        )

    def _render_page(
        self,
        *,
        pdf_path: Path,
        filename: str,
        work_dir: Path,
        cache_dir: Path,
        page_number: int,
        dpi: int,
    ) -> PageImage:
        output_prefix = work_dir / f"page-{page_number}"
        try:
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-singlefile",
                    "-f",
                    str(page_number),
                    "-l",
                    str(page_number),
                    "-r",
                    str(dpi),
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
                    "page_number": page_number,
                    "exit_code": exc.returncode,
                    "stderr": (exc.stderr or "").strip()[:1000],
                },
            ) from exc

        rendered_file = work_dir / f"page-{page_number}.png"
        if not rendered_file.is_file():
            raise ParserError(
                "PDF_RENDER_EMPTY",
                "PDF renderer produced no page images.",
                status_code=422,
                details={"filename": filename, "page_number": page_number},
            )

        final_path = cache_dir / f"{pdf_path.stem}-{work_dir.name}-page-{page_number}.png"
        shutil.copyfile(rendered_file, final_path)
        with Image.open(final_path) as image:
            width, height = image.size

        return PageImage(
            number=page_number,
            width=width,
            height=height,
            image_path=str(final_path),
        )
