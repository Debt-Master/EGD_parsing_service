from egd_parser.pipeline.extractors.page2_residents import (
    annotate_without_registration,
)


def test_annotate_without_registration_detects_marker() -> None:
    block = {
        "count": 1,
        "persons": [
            {
                "full_name": "Шведова Анна Вадимовна",
                "birthday_date": "14.11.1975",
                "__departure_raw_text": "без реги- страции",
            }
        ],
    }

    annotated = annotate_without_registration(block)

    assert annotated["persons"][0]["__registration_status"] == "unregistered"
    assert annotated["persons"][0]["__registration_status_raw"] == "без реги- страции"
