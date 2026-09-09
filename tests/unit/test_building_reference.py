import json

import pytest

from egd_parser.api.building_reference import parse_building_reference
from egd_parser.application.errors import ParserError
from egd_parser.domain.models.ocr import OCRPageResult
from egd_parser.pipeline.extractors.page1 import extract_page1


def test_db_realty_reference_repairs_corrupted_street_and_uses_canonical_fields() -> None:
    reference = parse_building_reference(json.dumps({
        "version": "2026-09-09T10:00:00Z",
        "buildings": [{
            "reference_id": "realty-building-9",
            "kladr": "01770000000000203",
            "street": "Новочеркасский",
            "house": "9",
            "building": None,
            "structure": None,
        }],
    }, ensure_ascii=False))
    text = """
    Заявитель зарегистрирован по месту жительства:
    ул. Новочеркасsкий бульвар дом № 9 кв. 111
    Прежнее наименование адреса:
    Вид заселения:
    частная собственность
    """

    address = extract_page1(
        [OCRPageResult(page_number=1, text=text)], reference
    )["page_1"]["property_address"]

    assert address["street"] == "Новочеркасский"
    assert address["house"] == "9"
    assert address["apartment"] == "111"
    assert address["__reference__"] == {
        "mode": "db_realty",
        "matched": True,
        "kladr": "01770000000000203",
        "reference_id": "realty-building-9",
        "version": "2026-09-09T10:00:00Z",
    }


def test_db_realty_reference_does_not_guess_another_house() -> None:
    reference = parse_building_reference(
        '[{"street":"Донецкая","house":"1","kladr":"01770000000000165"}]'
    )
    text = """
    Заявитель зарегистрирован по месту жительства:
    ул. Донеская дом № 11 кв. 260
    Прежнее наименование адреса:
    Вид заселения:
    частная собственность
    """

    address = extract_page1(
        [OCRPageResult(page_number=1, text=text)], reference
    )["page_1"]["property_address"]

    assert address["house"] == "11"
    assert address["__reference__"]["matched"] is False


def test_db_realty_reference_requires_unique_building_match() -> None:
    reference = parse_building_reference("""[
      {"street":"Подольская","house":"27","building":"1"},
      {"street":"Подольская","house":"27","building":"2"}
    ]""")
    text = """
    Заявитель зарегистрирован по месту жительства:
    ул. Подольская дом № 27 кв. 10
    Прежнее наименование адреса:
    Вид заселения:
    частная собственность
    """

    address = extract_page1(
        [OCRPageResult(page_number=1, text=text)], reference
    )["page_1"]["property_address"]

    assert address["__reference__"]["matched"] is False


@pytest.mark.parametrize("raw", ["not-json", "[]", '[{"street":"Донецкая"}]'])
def test_invalid_db_realty_reference_is_rejected(raw: str) -> None:
    with pytest.raises(ParserError) as caught:
        parse_building_reference(raw)
    assert caught.value.code == "INVALID_ADDRESS_REFERENCE"
