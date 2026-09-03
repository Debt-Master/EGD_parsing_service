from egd_parser.domain.models.ocr import OCRPageResult
from egd_parser.pipeline.extractors.page2 import extract_page2


def test_permanent_resident_pages_stop_after_temporary_section_starts() -> None:
    pages = [
        OCRPageResult(page_number=2, text="Фамилия, имя, отчество Дата рождения Паспорт"),
        OCRPageResult(
            page_number=3,
            text=(
                "Фамилия, имя, отчество Дата рождения Паспорт\n"
                "Кроме того, на данной площади зарегистрированы по месту пребывания:"
            ),
        ),
        OCRPageResult(
            page_number=4,
            text=(
                "Фамилия, имя, отчество Дата рождения Паспорт\n"
                "Временнова Анна 01.02.1990 Ивановна\n"
                "другой жилой площади не имеют/имеют"
            ),
        ),
    ]

    result = extract_page2(pages)

    assert result["__trace__"]["registered_persons_constantly"]["page_numbers"] == [2, 3]
    assert result["registered_persons_temporary"]["count"] == 1
    assert result["registered_persons_temporary"]["persons"][0]["full_name"] == "Временнова Анна Ивановна"
