"""The stored form of an accepted attribute assignment (#331, ADR 0011).

An annotation's accepted categorical values are an array of strings ``<attribute id>:<value id>``
(``Annotation.attributeValues``), each id a UUID in canonical lowercase form. Both parts have a
fixed length, so the encoding is unambiguous: no element is a prefix of another, a prefix
``<attribute id>:`` selects exactly the values of that attribute, and neither editable labels
nor punctuation in them take part in identity.
"""
import re
from uuid import UUID

SEPARATOR = ":"
_ENCODED = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                      r":[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def encode(attribute_id: UUID, value_id: UUID) -> str:
    return f"{UUID(str(attribute_id))}{SEPARATOR}{UUID(str(value_id))}"


def decode(encoded: str) -> tuple[UUID, UUID]:
    """The (attribute id, value id) of a stored element; ``ValueError`` for anything else."""
    if not _ENCODED.match(encoded):
        raise ValueError(f"Not an attribute assignment: {encoded!r}")
    attribute, value = encoded.split(SEPARATOR)
    return UUID(attribute), UUID(value)


def attribute_pattern(attribute_id: UUID) -> str:
    """The ``like`` pattern matching exactly the stored values of one attribute."""
    return f"{UUID(str(attribute_id))}{SEPARATOR}*"


def group(encoded: list[str] | None) -> dict[UUID, list[UUID]]:
    """Stored elements grouped by attribute (elements that do not decode are left out)."""
    grouped: dict[UUID, list[UUID]] = {}
    for element in encoded or []:
        try:
            attribute, value = decode(element)
        except ValueError:
            continue
        grouped.setdefault(attribute, []).append(value)
    return grouped
