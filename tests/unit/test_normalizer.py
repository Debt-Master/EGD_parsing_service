"""Unit tests for EGD normalizer (план 2.1, доводки)."""

from __future__ import annotations

from egd_parser.api.normalizer import normalize


def _make_response(**page_1_overrides):
    page_1 = {
        "document_date": "01.01.2024",
        "administrative_okrug": "ЦАО",
        "district": "Тверской",
        "passport": {
            "series": "1234",
            "number": "567890",
            "issued_by": "ОВД Тверской",
            "issue_date": "10.05.2020",
        },
        "property_address": {"full": "ул. Тверская, д. 1, кв. 2"},
        "management_company": {
            "name": "ООО \"УК Тверская\"",
            "inn": "7707083893",
            "ogrn": "1027700132195",
        },
        "settlement_type": "частная собственность",
        "owners": [{"full_name": "Иванов Иван Иванович", "ownership_share": "100%"}],
        "ownership_documents": ["Свидетельство 77 АА 123456 от 10.01.2010"],
        "total_area_sq_m": 45.0,
    }
    page_1.update(page_1_overrides)
    return {
        "filename": "test.pdf",
        "extracted_data": {"page_1": page_1, "page_2": {}},
        "metadata": {},
    }


def test_administrative_okrug_promoted_to_top_level():
    out = normalize(_make_response())
    assert out["administrative_okrug"] == "ЦАО"


def test_ownership_documents_promoted_to_top_level():
    out = normalize(_make_response())
    assert out["ownership_documents"] == ["Свидетельство 77 АА 123456 от 10.01.2010"]
    # Also kept in metadata for backward compatibility
    assert out["metadata"]["ownership_documents"] == [
        "Свидетельство 77 АА 123456 от 10.01.2010"
    ]


def test_document_date_uses_passport_issue_date():
    """document_date should prefer passport issue_date for SCD-2 identity tracking."""
    out = normalize(_make_response())
    assert out["document_date"] == "10.05.2020"


def test_document_date_falls_back_to_form_date_when_no_passport():
    out = normalize(_make_response(passport={}))
    assert out["document_date"] == "01.01.2024"


def test_management_company_is_dict_with_inn_ogrn():
    out = normalize(_make_response())
    mc = out["management_company"]
    assert isinstance(mc, dict)
    assert mc["name"] == 'ООО "УК Тверская"'
    assert mc["inn"] == "7707083893"
    assert mc["ogrn"] == "1027700132195"


def test_management_company_none_when_empty():
    out = normalize(_make_response(management_company={}))
    assert out["management_company"] is None


def test_ownership_documents_empty_list_when_absent():
    out = normalize(_make_response(ownership_documents=[]))
    assert out["ownership_documents"] == []
