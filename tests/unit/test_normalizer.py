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


def test_confirmed_name_correction_enriches_owner_without_duplicate():
    from egd_parser.pipeline.runner import normalize_registered_full_name

    response = _make_response(passport={}, owners=[{
        "full_name": "Смирнов Дмитрий Владимирович", "ownership_share": "37.50",
    }])
    response["extracted_data"]["page_2"] = {
        "registered_persons_constantly": {"persons": [{
            "full_name": normalize_registered_full_name("Смирнов Дмитрий Владимиробич"),
            "birthday_date": "03.12.1972", "registration_status": "registered",
            "passport": {"document_type": "паспорт", "series": "00 00", "number": "123456"},
        }]}
    }
    persons = normalize(response)["persons"]
    assert len(persons) == 1
    assert persons[0]["role"] == "owner"
    assert persons[0]["birthday_date"] == "03.12.1972"
    assert persons[0]["identity"]["number"] == "123456"


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


def test_primary_tenant_gets_occupancy_status_from_settlement_type():
    response = _make_response(
        settlement_type="социальный наем",
        owners=[],
        primary_tenant="Константинов Николай Алексеевич",
    )
    response["extracted_data"]["page_2"] = {
        "registered_persons_constantly": {
            "persons": [
                {
                    "full_name": "Константинов Николай Алексеевич",
                    "registration_status": "registered",
                }
            ]
        }
    }
    out = normalize(response)

    tenant = next(person for person in out["persons"] if person["role"] == "tenant")
    assert tenant["registration_status"] == "registered"
    assert tenant["settlement_type"] == "социальный наем"
    assert tenant["occupancy_status"] == "социальный наем"


def test_owner_is_enriched_from_matching_registered_person():
    response = _make_response(passport={})
    response["extracted_data"]["page_2"] = {
        "registered_persons_constantly": {
            "persons": [{
                "full_name": "Иванов Иван Иванович",
                "birthday_date": "01.02.1980",
                "registration_status": "unregistered",
                "passport": {
                    "document_type": "паспорт",
                    "series": "45 10",
                    "number": "123456",
                    "issued_by": "ОВД Марьино",
                    "issue_date": "03.04.2000",
                },
                "departure": {
                    "status": "departed",
                    "reason": "death",
                    "death_date": "05.06.2025",
                },
            }]
        }
    }

    persons = normalize(response)["persons"]
    owner = next(person for person in persons if person["role"] == "owner")

    assert owner["birthday_date"] == "01.02.1980"
    assert owner["registration_status"] == "without_registration"
    assert owner["identity"]["series"] == "45 10"
    assert owner["occupancy_status"] == "deceased"
    assert owner["departure"] == {
        "status": "departed",
        "reason": "death",
        "death_date": "05.06.2025",
        "departure_date": None,
    }
    assert [person["full_name"] for person in persons].count("\u0418\u0432\u0430\u043d\u043e\u0432 \u0418\u0432\u0430\u043d \u0418\u0432\u0430\u043d\u043e\u0432\u0438\u0447") == 1


def test_duplicate_registered_person_is_emitted_once():
    response = _make_response()
    duplicate = {
        "full_name": "Амбарцумян Арианна Арменаковна",
        "birthday_date": "01.02.1990",
        "registration_status": "registered",
    }
    response["extracted_data"]["page_2"] = {
        "registered_persons_constantly": {"persons": [duplicate, dict(duplicate)]}
    }

    persons = normalize(response)["persons"]

    assert [person["full_name"] for person in persons].count(
        "Амбарцумян Арианна Арменаковна"
    ) == 1


def test_compound_surname_is_kept_in_structured_name():
    response = _make_response(owners=[{
        "full_name": "\u0414\u0435 \u0411\u0443\u0430\u0440\u0434 \u0413\u0430\u043b\u0438\u043d\u0430 \u041f\u0435\u0442\u0440\u043e\u0432\u043d\u0430",
        "ownership_share": "50.00",
    }])

    owner = normalize(response)["persons"][0]

    assert owner["last_name"] == "\u0414\u0435 \u0411\u0443\u0430\u0440\u0434"
    assert owner["first_name"] == "\u0413\u0430\u043b\u0438\u043d\u0430"
    assert owner["middle_name"] == "\u041f\u0435\u0442\u0440\u043e\u0432\u043d\u0430"


def test_temporary_registered_person_has_distinct_status():
    response = _make_response()
    response["extracted_data"]["page_2"] = {
        "registered_persons_temporary": {
            "persons": [{
                "full_name": "Временный Житель Петрович",
                "birthday_date": "10.11.1990",
                "registration_status": "registered",
            }]
        }
    }

    temporary = next(
        person for person in normalize(response)["persons"]
        if person["role"] == "registered_temporary"
    )

    assert temporary["registration_status"] == "temporary"


def test_patronymic_suffix_is_kept_in_structured_name():
    response = _make_response(owners=[{
        "full_name": "Пириев Хайям Идрис оглы",
        "ownership_share": "25.00",
    }])

    owner = normalize(response)["persons"][0]

    assert owner["last_name"] == "Пириев"
    assert owner["first_name"] == "Хайям"
    assert owner["middle_name"] == "Идрис оглы"


def test_page1_passport_is_not_assigned_to_first_of_multiple_owners():
    response = _make_response(owners=[
        {"full_name": "Первый Собственник Петрович", "ownership_share": "50.00"},
        {"full_name": "Второй Собственник Иванович", "ownership_share": "50.00"},
    ])

    owners = [person for person in normalize(response)["persons"] if person["role"] == "owner"]

    assert owners[0]["identity"] is None
    assert owners[1]["identity"] is None
