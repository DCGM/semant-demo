"""Document metadata of one Kramerius metadata-mirror record, normalized (#257).

The mirror (``meta_records`` in the ``librarymetadata`` PostgreSQL database) holds one row
per ``(id, library)``. ``map_record`` reads one such row only: values are never combined
from rows of other libraries, and a value the row lacks stays absent.

``metadata_json`` comes from the MODS parser: each key holds the values of the record and
of its ancestors, usually as nested lists, own values first. ``values`` flattens any
nesting depth-first, so the record's own value wins and the order is stable.

A periodical item's ``title`` may hold only its issue number (``mzk``: "12"), so ``title``
is composed from the record and its ancestors in the same library (``compose_title``).
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SourceRecord:
    """The columns of one ``meta_records`` row used for document metadata."""
    id: str
    library: str
    public: bool | None = None
    in_library: bool | None = None
    record_type: str | None = None
    title: str | None = None
    date: str | None = None
    start_date: datetime | date | None = None
    end_date: datetime | date | None = None
    metadata_json: Mapping[str, Any] | None = None
    parent_id: str | None = None
    parent_library: str | None = None


def values(data: Any) -> list[str]:
    """The non-empty values of ``data`` (a scalar or arbitrarily nested lists), in order,
    without repeats."""
    found: list[str] = []

    def walk(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, (list, tuple)):
            for element in item:
                walk(element)
            return
        text = str(item).strip()
        if text and text not in found:
            found.append(text)

    walk(data)
    return found


def first(data: Any) -> str | None:
    found = values(data)
    return found[0] if found else None


@dataclass(frozen=True)
class IssueDate:
    """A publication date with only the precision the source states."""
    date: datetime | None = None
    """Midnight UTC of the day; only when the source names the day."""
    year: int | None = None


_APPROXIMATE = re.compile(r"^(?:ca\.?|cca\.?|c\.|asi)\s*", re.IGNORECASE)
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})$")
_ISO_DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_MONTH_YEAR = re.compile(r"^(?:(\d{1,2})[./]\s*(\d{4})|(\d{4})-(\d{2}))$")
_YEAR = re.compile(r"^(\d{4})$")


def _day(year: str, month: str, day: str) -> IssueDate:
    try:
        return IssueDate(datetime(int(year), int(month), int(day), tzinfo=timezone.utc), int(year))
    except ValueError:  # not a calendar day
        return IssueDate()


def parse_issue_date(text: str | None, start: datetime | date | None = None,
                     end: datetime | date | None = None) -> IssueDate:
    """The day and/or year of a free-text date such as ``22.5.1929``, ``1929-05-22``,
    ``5.1929``, ``1929``, ``[1929?]`` or ``asi 1929``.

    A year or month gives only the year, never an invented day. A range, open range or
    partial year (``1890-1895``, ``1890-``, ``189-``) or an unparsed text (the mirror's
    ``not_found``) gives nothing from the text; then the mirror's parsed ``start``/``end``
    are used: equal values give that day (except 1 January, possibly a year-only value),
    values in one year give the year. ``start`` alone is not used, because the mirror stores
    a point date (a year as 1 January) and an open range the same way.
    """
    if text:
        cleaned = _APPROXIMATE.sub("", re.sub(r"[\[\]?]", "", text).strip())
        if match := _DAY_MONTH_YEAR.match(cleaned):
            day, month, year = match.groups()
            return _day(year, month, day)
        if match := _ISO_DAY.match(cleaned):
            return _day(*match.groups())
        if match := _MONTH_YEAR.match(cleaned):
            month = int(match.group(1) or match.group(4))
            return IssueDate(year=int(match.group(2) or match.group(3))) if 1 <= month <= 12 else IssueDate()
        if match := _YEAR.match(cleaned):
            return IssueDate(year=int(match.group(1)))
    if start is not None and end is not None and start.year == end.year:
        if start == end and (start.month, start.day) != (1, 1):
            return _day(str(start.year), str(start.month), str(start.day))
        return IssueDate(year=start.year)
    return IssueDate()


FIELDS = (
    "title", "titleMetadata", "subtitle", "partNumber", "partName", "dateIssued", "yearIssued",
    "dateIssuedMetadata", "yearIssuedMetadata", "author", "publisher", "language", "documentType",
    "placeOfPublication", "seriesName", "seriesNumber", "edition", "manufacturePublisher",
    "manufacturePlaceTerm", "illustrators", "translators", "editors", "redaktors", "public", "library",
)
"""Every field ``map_record`` can return."""


def _own(value: Any) -> str | None:
    """The first own value of a MODS key: the first group when the values are nested by level
    (record first, then its ancestors), else the first value."""
    if isinstance(value, list) and value and isinstance(value[0], list):
        value = value[0]
    return first(value)


def own_title(record: SourceRecord) -> str | None:
    """The title of the record's own level: the ``title`` column, else its own MODS title,
    else, for a part of a parent record (a volume or issue), its own MODS part number."""
    meta = record.metadata_json or {}
    title = first(record.title) or _own(meta.get("Title"))
    return title or (_own(meta.get("PartNumber")) if record.parent_id else None)


_LEADING = " .,:;/-"
_TRAILING = " ,:;/"
_MAIN_TITLE_END = ".:;/"
NEAR_DUPLICATE_DISTANCE = 2
NEAR_DUPLICATE_MIN_LENGTH = 6
"""Shorter titles (issue and volume numbers, years) are compared only for equality."""


def _distance(a: str, b: str, limit: int) -> int:
    """Levenshtein distance, or ``limit + 1`` when it exceeds ``limit``."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _same(a: str, b: str) -> bool:
    a, b = a.casefold(), b.casefold()
    if a == b:
        return True
    return min(len(a), len(b)) >= NEAR_DUPLICATE_MIN_LENGTH and \
        _distance(a, b, NEAR_DUPLICATE_DISTANCE) <= NEAR_DUPLICATE_DISTANCE


def _ends_main_title(text: str, at: int) -> bool:
    rest = text[at:].lstrip()
    return not rest or rest[0] in _MAIN_TITLE_END


def _repeated_main_title(title: str, part: str) -> int:
    """The length of the longest leading piece of ``title`` that is a main title of ``part``
    (``part`` up to a ``.``, ``:``, ``;`` or ``/``, or all of it) and ends a main title in
    ``title`` too; 0 if none. "Právo lidu. 183" repeats "Právo lidu" of "Právo lidu: časopis…"."""
    folded, part_folded = title.casefold(), part.casefold()
    for end in range(len(part), 0, -1):
        if end < len(part) and part[end] not in _MAIN_TITLE_END:
            continue
        main = part_folded[:end].rstrip()
        if main and folded.startswith(main) and _ends_main_title(title, len(main)):
            return len(main)
    return 0


def _starts_with(text: str, prefix: str) -> bool:
    """``text`` begins with ``prefix`` as whole words (``"1932"`` does not begin with ``"1"``)."""
    return len(text) > len(prefix) and text.casefold().startswith(prefix.casefold()) \
        and not text[len(prefix)].isalnum()


def compose_title(levels: list[str | None]) -> str | None:
    """One title from the titles of a record's levels, root first (e.g. periodical, volume,
    issue), joined by ``". "``.

    A level first loses a leading repeat of a kept main title (``"Křesťanská revue. 6"`` under
    ``"Křesťanská revue"`` adds ``"6"``; ``"Právo lidu. 183"`` under ``"Právo lidu: časopis…"``
    adds ``"183"``). Each of its ``". "``-separated pieces is then left out if it differs by at
    most 2 characters from a kept piece (case-insensitively; pieces under 6 characters only
    if equal), or a kept piece begins with it (a shortened variant).
    """
    kept: list[str] = []
    for level in levels:
        title = (level or "").lstrip(_LEADING).rstrip(_TRAILING)
        for part in kept:
            if repeated := _repeated_main_title(title, part):
                title = title[repeated:].lstrip(_LEADING)
        for piece in title.split(". "):
            piece = piece.lstrip(_LEADING).rstrip(_TRAILING)
            if piece and not any(_same(piece, part) or _starts_with(part, piece) for part in kept):
                kept.append(piece)
    return "".join(part if not i else (" " if kept[i - 1].endswith(".") else ". ") + part
                   for i, part in enumerate(kept)) or None


def map_record(record: SourceRecord, ancestors: Sequence[SourceRecord] = ()) -> dict[str, Any]:
    """The document metadata of one mirror row, by application field name.

    Fields the row has no value for are left out. ``title`` is composed from the row's and
    its ``ancestors``' (same library, root first) own titles; ``dateIssued`` and
    ``yearIssued`` come from the row's own columns, else from its MODS values;
    ``titleMetadata``, ``dateIssuedMetadata`` and ``yearIssuedMetadata`` keep the MODS
    values. A day is kept only if it lies in the chosen year.
    """
    meta = record.metadata_json or {}
    own_date = parse_issue_date(first(record.date), record.start_date, record.end_date)
    mods_date = parse_issue_date(first(meta.get("DateIssued")))
    year = own_date.year if own_date.year is not None else mods_date.year
    day = own_date.date or mods_date.date
    if day is not None and day.year != year:
        day = None

    mapped: dict[str, Any] = {
        "title": compose_title([own_title(level) for level in (*ancestors, record)]),
        "titleMetadata": first(meta.get("Title")),
        "subtitle": first(meta.get("Subtitle")),
        "partNumber": first(meta.get("PartNumber")),
        "partName": first(meta.get("PartName")),
        "dateIssued": day,
        "yearIssued": year,
        "dateIssuedMetadata": mods_date.date,
        "yearIssuedMetadata": mods_date.year,
        "author": values(meta.get("Author")),
        "publisher": first(meta.get("Publisher")),
        "language": first(meta.get("Language")),
        "documentType": first(record.record_type),
        "placeOfPublication": first(meta.get("PlaceTerm")),
        "seriesName": first(meta.get("SeriesName")),
        "seriesNumber": first(meta.get("SeriesNumber")),
        "edition": first(meta.get("Edition")),
        "manufacturePublisher": first(meta.get("ManufacturePublisher")),
        "manufacturePlaceTerm": first(meta.get("ManufacturePlaceTerm")),
        "illustrators": values(meta.get("Illustrator")),
        "translators": values(meta.get("Translator")),
        "editors": values(meta.get("Editor")),
        "redaktors": values(meta.get("Redaktor")),
        "public": record.public,
        "library": record.library,
    }
    return {name: value for name, value in mapped.items() if value not in (None, [])}
