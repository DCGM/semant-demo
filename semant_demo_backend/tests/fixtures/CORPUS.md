# Fixture corpus quick reference

A map for choosing valid combinations in fixture-dependent tests. [`corpus.json`](corpus.json)
is authoritative, and [`tests/corpus.py`](../corpus.py) validates it on load. Use corpus keys
from there instead of copying IDs or text from here.

## Documents and chunk membership

| Document | Document collections | Chunks and their collections |
| --- | --- | --- |
| `chronicle` | `chronicles`, `newspapers` | `chronicle_1`, `chronicle_2`: `chronicles`; `chronicle_3`: `newspapers` |
| `letters` | `chronicles` | `letters_1`, `letters_2`: `chronicles` |
| `gazette` | `newspapers`, `outsider_notes` | `gazette_1`: `newspapers`, `outsider_notes`; `gazette_2`: `newspapers` |

Every fixture document is public (`public: true`), so suites that test other behavior see the
whole corpus without a collection. Tests of the document access rule (#279) make a document
restricted (`false`) or unknown (no value) themselves, for example
`tests/integration/test_document_rights.py`.

A chunk's collections are a subset of its document's. The subset can be smaller: for example,
`chronicle_3` is not in `chronicles`, although its document is.

## Tags

| Tag | Owning collection |
| --- | --- |
| `person`, `place` | `chronicles` (owned by `owner`, shared with `annotator`) |
| `event` | `newspapers` (owned by `owner`, not shared) |
| `outsider_tag` | `outsider_notes` (owned by `outsider`) |

Annotations are scoped to a collection. A span or annotation needs a tag from that collection
and a chunk that is itself a member of it; document membership alone is not enough. For
example, `event` fits `chronicle_3`, `gazette_1` and `gazette_2`, but not `chronicle_1`.

## Intentional Unicode edge cases

These are deliberate test cases, not assumptions about production text:

- **Decomposed (NFD) characters.** `letters_2` writes `Zdeňku` with `n` + combining caron
  (U+030C), and `gazette_1` writes `Café` with `e` + combining acute accent (U+0301). Do not
  compare them with precomposed literals unless the test normalizes both sides.
- **Non-BMP character.** `letters_2` ends with 😀 (U+1F600), one Python code point but two
  JavaScript UTF-16 code units.
- **Span offsets** are Python code-point indices. Every fixture span ends before any non-BMP
  character in its chunk, so the same offsets are valid JavaScript UTF-16 indices.
  `tests/corpus.py` asserts both properties.
