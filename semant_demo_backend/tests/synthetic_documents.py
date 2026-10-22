"""Synthetic metadata-only documents for the local development store (#361).

The seeded corpus has three documents, too few to try the corpus overview's filters or to
measure its aggregates. ``python -m tests.local_dev add-documents`` (``make
dev-add-documents``) inserts these documents next to it: bibliographic metadata only, no
chunks, collection membership or vectors, so they appear in the corpus overview but not in
Search or Document view.

Document ``n`` is always the same (its own random generator, seeded with ``n``), so a
larger count adds only further documents. The ids share the prefix ``SYNTHETIC_PREFIX``,
which the fixture corpus does not use; ``make dev-verify`` tells them apart by it.

The distributions are plausible, not measured: years 1600–2000, mostly 1850–1940, with some
missing; four source libraries and five language codes (``ces`` and its alias ``cze``, which
share a display name) with some missing; Czech, German and Latin titles. The two outliers
mirror the real corpus, which holds one document from 311 and one from 2879.
"""
from __future__ import annotations

import random
from collections.abc import Iterator
from uuid import UUID

SYNTHETIC_PREFIX = "5e3a5d0c-"
MAX_COUNT = 1_000_000

_LIBRARIES = [("mzk", 45), ("nkp", 30), ("svkhk", 8), ("vkol", 7), (None, 10)]
_LANGUAGES = [("ces", 68), ("deu", 15), ("lat", 5), ("slk", 3), ("cze", 2), (None, 7)]
_TYPES = [("BOOK", 55), ("PERIODICAL", 30), ("LETTER", 10), ("MAP", 5)]
_MISSING_YEAR = 0.05

_BOOK_SUBJECTS = ["Kronika", "Dějiny", "Paměti", "Popis", "Průvodce po", "Zpráva o stavu", "Sborník",
                  "Kázání", "Listy z", "Obrázky z"]
_BOOK_OBJECTS = ["obce Lhota", "města Brna", "království českého", "Moravy", "pražské university",
                 "školy v Kutné Hoře", "rodu Šternberků", "kraje plzeňského", "farnosti svatého Jakuba",
                 "Slezska", "Českomoravské vysočiny", "Žižkova"]
_BOOK_SUFFIXES = ["", "", "", " a okolí", " v letech války", " pro lid", " s mapou"]
_PERIODICALS = {"ces": ["Pražský věstník", "Moravská orlice", "Národní listy", "Lidové noviny", "Česká včela",
                        "Škola a život", "Zlatá Praha", "Brněnské noviny"],
                "slk": ["Slovenské noviny", "Národnie noviny"],
                "deu": ["Prager Zeitung", "Brünner Zeitung", "Bohemia"],
                "lat": ["Acta Universitatis Carolinae"]}
_PERIODICAL_PARTS = {"ces": ("Ročník", "Číslo"), "slk": ("Ročník", "Číslo"), "deu": ("Jahrgang", "Nummer"),
                     "lat": ("Volumen", "Numerus")}
_GERMAN_TITLES = ["Geschichte der Stadt Brünn", "Beschreibung des Königreichs Böhmen", "Mährische Chronik",
                  "Reise durch Schlesien", "Gedichte"]
_LATIN_TITLES = ["Historia Bohemica", "Chronica Boemorum", "Legenda sancti Wenceslai", "Annales Pragenses"]
_PEOPLE = ["Jan Novák", "František Palacký", "Božena Němcová", "Karel Havlíček", "Josef Dobrovský",
           "Marie Černá", "Václav Hájek z Libočan", "Alois Jirásek"]
_RECIPIENTS = ["Františku Palackému", "Boženě Němcové", "Josefu Jungmannovi", "městské radě v Brně"]
_REGIONS = ["Čech", "Moravy", "okolí Prahy", "Slezska", "kraje táborského"]
_PLACES = ["Praha", "Brno", "Olomouc", "Vídeň", "Hradec Králové", "Litomyšl"]
_PUBLISHERS = ["J. Otto", "F. Šimáček", "Matice česká", "Vilímek", None, None]

# The real corpus has exactly these two (#361): one probably a manuscript copy, one a typo.
_OUTLIERS = [
    {"title": "Legenda o svatém Václavovi", "yearIssued": 311, "library": "nkp", "language": "lat",
     "documentType": "BOOK", "public": True},
    {"title": "Národní listy. Ročník 19. Číslo 4", "yearIssued": 2879, "library": "mzk", "language": "ces",
     "documentType": "PERIODICAL", "public": True},
]


def synthetic_id(n: int) -> UUID:
    """The id of generated document ``n`` (0-based)."""
    return UUID(f"{SYNTHETIC_PREFIX}0000-4000-8000-{n:012x}")


def outlier_id(n: int) -> UUID:
    return UUID(f"{SYNTHETIC_PREFIX}0000-4000-8001-{n:012x}")


def is_synthetic(uuid: UUID | str) -> bool:
    return str(uuid).startswith(SYNTHETIC_PREFIX)


def _pick(rng: random.Random, weighted: list[tuple[str | None, int]]) -> str | None:
    return rng.choices([value for value, _ in weighted], weights=[w for _, w in weighted])[0]


def _year(rng: random.Random) -> int | None:
    if rng.random() < _MISSING_YEAR:
        return None
    if rng.random() < 0.7:
        return min(2000, max(1600, round(rng.gauss(1895, 22))))
    return rng.randint(1600, 2000)


def _title(rng: random.Random, document_type: str, language: str | None) -> str:
    language = {"cze": "ces", None: "ces"}.get(language, language)
    if document_type == "PERIODICAL":
        volume, number = _PERIODICAL_PARTS[language]
        return f"{rng.choice(_PERIODICALS[language])}. {volume} {rng.randint(1, 60)}. {number} {rng.randint(1, 52)}"
    if language == "deu":
        return rng.choice(_GERMAN_TITLES)
    if language == "lat":
        return rng.choice(_LATIN_TITLES)
    if document_type == "LETTER":
        return f"Dopis {rng.choice(_PEOPLE)} {rng.choice(_RECIPIENTS)}"
    if document_type == "MAP":
        return f"Mapa {rng.choice(_REGIONS)}"
    return f"{rng.choice(_BOOK_SUBJECTS)} {rng.choice(_BOOK_OBJECTS)}{rng.choice(_BOOK_SUFFIXES)}"


def synthetic_document(n: int) -> dict:
    """The properties of generated document ``n``; a missing value is an absent key."""
    rng = random.Random(f"semant-synthetic-document-{n}")
    document_type = _pick(rng, _TYPES)
    language = _pick(rng, _LANGUAGES)
    properties = {
        "title": _title(rng, document_type, language),
        "yearIssued": _year(rng),
        "library": _pick(rng, _LIBRARIES),
        "language": language,
        "documentType": document_type,
        "placeOfPublication": rng.choice(_PLACES),
        "publisher": rng.choice(_PUBLISHERS),
        "public": True,
    }
    if document_type in ("BOOK", "LETTER"):
        properties["author"] = [rng.choice(_PEOPLE)]
    return {key: value for key, value in properties.items() if value is not None}


def synthetic_documents(count: int, outliers: bool) -> Iterator[tuple[UUID, dict]]:
    """``count`` generated documents, then (with ``outliers``) the two outlier years."""
    if not 0 <= count <= MAX_COUNT:
        raise ValueError(f"count must be between 0 and {MAX_COUNT}")
    for n in range(count):
        yield synthetic_id(n), synthetic_document(n)
    if outliers:
        for n, properties in enumerate(_OUTLIERS):
            yield outlier_id(n), dict(properties)
