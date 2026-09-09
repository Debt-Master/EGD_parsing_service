from __future__ import annotations

import json
from typing import Any

from egd_parser.application.errors import ParserError
from egd_parser.domain.reference.buildings import ManagedBuilding, canonicalize_building_address_part


def parse_building_reference(raw: str | None) -> list[ManagedBuilding] | None:
    """Parse the per-request snapshot exported from db.realty/db.address."""
    if raw is None:
        return None
    try:
        payload: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise _invalid_reference("address_reference must be valid JSON") from exc

    version = _text(payload.get("version")) if isinstance(payload, dict) else None
    rows = payload.get("buildings") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise _invalid_reference("address_reference must contain a non-empty buildings list")

    result: list[ManagedBuilding] = []
    seen: set[tuple[str, str, str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise _invalid_reference(f"address_reference row {index} must be an object")
        street = _text(row.get("street"))
        house = _text(row.get("house"))
        if not street or not house:
            raise _invalid_reference(f"address_reference row {index} requires street and house")
        building = _text(row.get("building"))
        structure = _text(row.get("structure"))
        key = tuple(
            canonicalize_building_address_part(value or "")
            for value in (street, house, building, structure)
        )
        if key in seen:
            raise _invalid_reference(f"address_reference contains duplicate building at row {index}")
        seen.add(key)
        result.append(
            ManagedBuilding(
                full_address=_text(row.get("full_address")) or "",
                street=street,
                house=house,
                building=building,
                area_sq_m="",
                management_start_date="",
                structure=structure,
                kladr=_text(row.get("kladr")),
                reference_id=_text(row.get("reference_id")),
                reference_version=version,
            )
        )
    return result


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _invalid_reference(message: str) -> ParserError:
    return ParserError("INVALID_ADDRESS_REFERENCE", message, status_code=400)
