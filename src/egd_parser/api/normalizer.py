"""Convert EGD ParseResponse to unified parsed_document format."""

from __future__ import annotations
from typing import Any


def _split_name(full_name: str | None) -> dict[str, str | None]:
    if not full_name:
        return {"last_name": None, "first_name": None, "middle_name": None}
    parts = full_name.strip().split()
    if len(parts) > 3 and parts[-1].lower() in {"оглы", "кызы", "улы", "уулу"}:
        return {
            "last_name": parts[0],
            "first_name": parts[1],
            "middle_name": " ".join(parts[2:]),
        }
    if len(parts) > 3:
        return {
            "last_name": " ".join(parts[:-2]),
            "first_name": parts[-2],
            "middle_name": parts[-1],
        }
    return {
        "last_name": parts[0] if len(parts) > 0 else None,
        "first_name": parts[1] if len(parts) > 1 else None,
        "middle_name": parts[2] if len(parts) > 2 else None,
    }


def _normalize_identity(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not doc or not any(doc.get(k) for k in ("series", "number", "issued_by")):
        return None
    return {
        "document_type": doc.get("document_type"),
        "series": doc.get("series"),
        "number": doc.get("number"),
        "issued_by": doc.get("issued_by"),
        "issue_date": doc.get("issue_date"),
    }


def _normalize_departure(dep: dict[str, Any] | None) -> dict[str, Any] | None:
    if not dep or not dep.get("status"):
        return None
    return {
        "status": dep.get("status"),
        "reason": dep.get("reason"),
        "death_date": dep.get("death_date"),
        "departure_date": dep.get("departure_date"),
    }


def _canonical_name(value: str | None) -> str:
    return " ".join(str(value or "").replace("ё", "е").lower().split())


def _registration_status(value: str | None, *, temporary: bool = False) -> str:
    if temporary:
        return "temporary"
    normalized = str(value or "").strip().lower()
    if normalized in {"unregistered", "without_registration"}:
        return "without_registration"
    return normalized or "registered"


def _occupancy_status(departure: dict[str, Any] | None) -> str | None:
    if not departure or not departure.get("status"):
        return None
    if departure.get("reason") == "death":
        return "deceased"
    return departure.get("status")


def _build_page2_person_index(page_2: dict[str, Any]) -> dict[str, tuple[dict[str, Any], bool]]:
    persons: dict[str, tuple[dict[str, Any], bool]] = {}
    for block_name, temporary in (
        ("registered_persons_constantly", False),
        ("registered_persons_temporary", True),
    ):
        for person in page_2.get(block_name, {}).get("persons", []):
            key = _canonical_name(person.get("full_name"))
            if key and (key not in persons or not temporary):
                persons[key] = (person, temporary)
    return persons


def _build_registration_status_index(page_2: dict[str, Any]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for reg_type, default_status in [
        ("registered_persons_constantly", "registered"),
        ("registered_persons_temporary", "temporary"),
    ]:
        block = page_2.get(reg_type, {})
        for person in block.get("persons", []):
            full_name = person.get("full_name")
            if not full_name:
                continue
            statuses[full_name] = _registration_status(
                person.get("registration_status") or default_status,
                temporary=reg_type == "registered_persons_temporary",
            )
    return statuses


def _normalize_management_company(mc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not mc:
        return None
    if not any(mc.get(k) for k in ("name", "inn", "ogrn", "address", "phone")):
        return None
    return {
        "name": mc.get("name"),
        "inn": mc.get("inn"),
        "ogrn": mc.get("ogrn"),
        "address": mc.get("address"),
        "phone": mc.get("phone"),
    }


def _normalize_persons(data: dict[str, Any]) -> list[dict[str, Any]]:
    persons = []
    page_1 = data.get("page_1", {})
    page_2 = data.get("page_2", {})
    registration_statuses = _build_registration_status_index(page_2)
    page2_persons = _build_page2_person_index(page_2)
    settlement_type = page_1.get("settlement_type")
    primary_roles = {
        _canonical_name(owner.get("full_name"))
        for owner in page_1.get("owners", [])
        if owner.get("full_name")
    }
    if page_1.get("primary_tenant"):
        primary_roles.add(_canonical_name(page_1["primary_tenant"]))

    passport = page_1.get("passport", {})
    owners = page_1.get("owners", [])
    for owner in owners:
        matched, is_temporary = page2_persons.get(_canonical_name(owner.get("full_name")), ({}, False))
        matched_departure = _normalize_departure(matched.get("departure"))
        owner_identity = _normalize_identity(matched.get("passport"))
        if len(owners) == 1 and owner_identity is None and _normalize_identity(passport):
            owner_identity = _normalize_identity(passport)
        person = {
            "role": "owner",
            "registration_status": _registration_status(
                registration_statuses.get(owner.get("full_name"), matched.get("registration_status")),
                temporary=is_temporary,
            ) if matched else "unknown",
            "settlement_type": settlement_type,
            "occupancy_status": _occupancy_status(matched_departure),
            "full_name": owner.get("full_name"),
            **_split_name(owner.get("full_name")),
            "birthday_date": matched.get("birthday_date"),
            "ownership_share": owner.get("ownership_share"),
            "identity": owner_identity,
            "departure": matched_departure,
        }
        persons.append(person)

    if page_1.get("primary_tenant"):
        persons.append({
            "role": "tenant",
            "registration_status": registration_statuses.get(page_1["primary_tenant"], "unknown"),
            "settlement_type": settlement_type,
            "occupancy_status": settlement_type,
            "full_name": page_1["primary_tenant"],
            **_split_name(page_1["primary_tenant"]),
            "birthday_date": None,
            "ownership_share": None,
            "identity": _normalize_identity(passport) if not page_1.get("owners") else None,
            "departure": None,
        })

    for reg_type, role in [
        ("registered_persons_constantly", "registered_permanent"),
        ("registered_persons_temporary", "registered_temporary"),
    ]:
        block = page_2.get(reg_type, {})
        for p in block.get("persons", []):
            # An owner/tenant is already represented by its primary legal role and
            # enriched from this page-2 row above.  Do not emit a second person that
            # downstream systems could incorrectly treat as another debtor.
            if _canonical_name(p.get("full_name")) in primary_roles:
                continue
            departure = _normalize_departure(p.get("departure"))
            persons.append({
                "role": role,
                "registration_status": _registration_status(
                    p.get("registration_status"),
                    temporary=reg_type == "registered_persons_temporary",
                ),
                "settlement_type": settlement_type,
                "occupancy_status": _occupancy_status(departure),
                "full_name": p.get("full_name"),
                **_split_name(p.get("full_name")),
                "birthday_date": p.get("birthday_date"),
                "ownership_share": None,
                "identity": _normalize_identity(p.get("passport")),
                "departure": departure,
            })

    return persons


def normalize(response: dict[str, Any]) -> dict[str, Any]:
    """Convert EGD ParseResponse dict to unified parsed_document format."""
    data = response.get("extracted_data", {})
    page_1 = data.get("page_1", {})
    page_2 = data.get("page_2", {})
    address = page_1.get("property_address", {})
    passport = page_1.get("passport", {}) or {}

    # document_date prefers passport issue_date (used as identity validFromDate
    # in the SQL callback); falls back to the form's own document_date if the
    # passport block is empty.
    document_date = passport.get("issue_date") or page_1.get("document_date")

    ownership_documents = page_1.get("ownership_documents") or []

    return {
        "document_type": "egd",
        "source_filename": response.get("filename"),
        "address": {
            "raw": address.get("full"),
            "street": address.get("street"),
            "house": address.get("house"),
            "building": address.get("building"),
            "structure": address.get("structure"),
            "apartment": address.get("apartment"),
        },
        "persons": _normalize_persons(data),
        "management_company": _normalize_management_company(page_1.get("management_company")),
        "property_type": page_1.get("settlement_type"),
        "benefits": page_2.get("benefits"),
        "billing": None,
        "administrative_okrug": page_1.get("administrative_okrug"),
        "district": page_1.get("district"),
        "total_area_sq_m": page_1.get("total_area_sq_m"),
        "document_date": document_date,
        "ownership_documents": ownership_documents,
        "validations": response.get("metadata", {}).get("extraction_trace"),
        "metadata": {
            "ocr_engine": response.get("metadata", {}).get("ocr_engine"),
            "pages": response.get("pages"),
            "warnings": response.get("warnings"),
            "ownership_documents": ownership_documents,
        },
    }
