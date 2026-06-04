from abc import ABC, abstractmethod
from collections.abc import Iterator

from egd_parser.domain.models.page import PageImage


class PDFRenderer(ABC):
    @abstractmethod
    def render(self, filename: str, content: bytes) -> list[PageImage]:
        raise NotImplementedError

    def render_iter(self, filename: str, content: bytes) -> Iterator[PageImage]:
        yield from self.render(filename, content)
