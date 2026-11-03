"""The legacy chunking (``db_benchmarks/semant/db_prepare_documents.py`` and
``prepare_documents.py``), reproduced with a trace of which line text went where.

Per page in order, per region (``parse``), the kept lines are those with text and
``conf > line_confidence``; a region's paragraph is its kept lines joined with ``\\n``. A
paragraph (or the rest of a split one) of at most 10 code points is dropped. A paragraph that
fits is appended as ``\\n\\n`` + paragraph, and closes the chunk when the chunk length before
it plus the paragraph length exceeds ``min_chunk_chars``. One that would exceed
``max_chunk_chars`` adds ``\\n``, then ``\\n`` + line, one line at a time, until the chunk has
``min_chunk_chars``; the rest of the paragraph goes to a new chunk. A trailing empty chunk is
dropped and every chunk is ``str.strip()``-ped. Lengths count code points.

The legacy code failed the whole document (no chunks were produced) when an overflow ran out
of lines, when a line with text had no ``conf``, or when there were no regions at all; these
are returned as ``failure``. An unparseable page also failed it (``convert``).
"""
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from semant_demo.maintenance.page_layout.parse import Page

SHORT_PARAGRAPH = 10
"""A paragraph of at most this many code points is dropped."""


@dataclass(frozen=True)
class Params:
    line_confidence: float = 0.6
    min_chunk_chars: int = 768
    max_chunk_chars: int = 1152

    def as_json(self) -> dict:
        return {"lineConfidence": self.line_confidence, "minChunkChars": self.min_chunk_chars,
                "maxChunkChars": self.max_chunk_chars}


@dataclass(frozen=True)
class Contribution:
    """One line's text in a chunk: ``start`` is its code point index in the chunk's raw
    (unstripped) text."""
    page_id: UUID
    region_index: int
    line_index: int
    line_id: str | None
    text: str
    start: int


@dataclass
class Chunk:
    raw: str
    legacy_start_page_id: UUID
    """The page the legacy code opened the chunk on (stored as ``start_page_id``); not
    always the page of its first character."""
    contributions: list[Contribution] = field(default_factory=list)

    @property
    def text(self) -> str:
        return self.raw.strip()

    @property
    def lead(self) -> int:
        """Code points removed from the start by the strip."""
        return len(self.raw) - len(self.raw.lstrip())


@dataclass
class Serialization:
    chunks: list[Chunk]
    failure: str | None = None
    """``overflow_out_of_lines``, ``missing_conf`` or ``no_regions``: the legacy code
    produced no chunks for the document."""


def _kept(page: Page, region_index: int, params: Params) -> list[tuple[int, object]]:
    lines = []
    for line_index, line in enumerate(page.regions[region_index].lines):
        if not line.text:
            continue
        if line.conf is None:
            raise _Failure("missing_conf")
        if line.conf > params.line_confidence:
            lines.append((line_index, line))
    return lines


class _Failure(Exception):
    pass


def serialize(pages: Sequence[Page], params: Params = Params()) -> Serialization:
    """The chunks of a document from its parsed pages in order (missing pages left out)."""
    chunks: list[Chunk] = []
    try:
        for page in pages:
            for region_index in range(len(page.regions)):
                if not chunks:
                    chunks.append(Chunk("", page.page_id))
                lines = _kept(page, region_index, params)
                while lines:
                    paragraph = "\n".join(line.text for _, line in lines)
                    if len(paragraph) <= SHORT_PARAGRAPH:
                        break
                    chunk = chunks[-1]

                    def add(line_index, line):
                        chunk.contributions.append(Contribution(page.page_id, region_index, line_index, line.id,
                                                                line.text, len(chunk.raw)))
                        chunk.raw += line.text

                    if len(chunk.raw) + len(paragraph) > params.max_chunk_chars:
                        chunk.raw += "\n"
                        while len(chunk.raw) < params.min_chunk_chars:
                            if not lines:
                                raise _Failure("overflow_out_of_lines")
                            chunk.raw += "\n"
                            add(*lines[0])
                            lines = lines[1:]
                        chunks.append(Chunk("", page.page_id))
                    else:
                        closes = len(chunk.raw) + len(paragraph) > params.min_chunk_chars
                        for i, (line_index, line) in enumerate(lines):
                            chunk.raw += "\n\n" if i == 0 else "\n"
                            add(line_index, line)
                        lines = []
                        if closes:
                            chunks.append(Chunk("", page.page_id))
        if not chunks:
            raise _Failure("no_regions")
    except _Failure as failure:
        return Serialization([], str(failure))
    if not chunks[-1].raw:
        chunks.pop()
    return Serialization(chunks)
