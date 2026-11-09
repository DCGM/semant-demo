# Real page fixtures (#546)

Excerpts of five public documents of the digitized library corpus, published 1839–1922, for
the page layout, anchor and text/scan correspondence tests. Loaded by
`semant_demo_backend/tests/real_pages.py`; used by `tests/test_real_pages.py`, the frontend's
`test/unit/realPages.spec.ts` and `test/e2e/realScans.spec.ts`. What the tests found and the
coverage on the whole sample: [PAGE_LAYOUT.md](../../../../docs/PAGE_LAYOUT.md#validation-on-real-material-546).

| Document | Library, year | Pages (index in the page list) | Case |
| --- | --- | --- | --- |
| `000070c8-2b2a-46f9-8052-1ce4b7dac249` *Intelligenzblatt zur Prager Zeitung* | nacr, 1839 | 0 (the whole document) | Every chunk exact. |
| `0002097a-2223-46b0-8507-bde4b059daaa` *Pilsner Tagblatt* | d, 1913 | 12 | Columns (31 regions), the most curved and skewed baselines of the sample, display type; scan included. |
| `00094a56-54af-4bd4-9559-c5601d81b15d` *Mittheilungen aus dem Vereine der Naturfreunde in Reichenberg* | kvkli, 1906 | 0–15 | Title page, blank pages (with OCR of bleed-through below the confidence threshold), plates with a repeated caption, a chunk across ten page breaks, chunks across page breaks of the text pages; scan of page 14 included. |
| `000b03e0-53d7-11ee-9c28-0050568d319f` *Karlínské listy* | mzk, 1904 | 1 | The legacy chunks hold the page twice; the copies get no anchor. |
| `00246353-3566-4e72-80a6-4019d8f94d59` *Freudenthaler Zeitung* | svkos, 1922 | 0 | The stored chunks are another, older OCR (Fraktur, long s): no anchor. |

Sources, read on 2026-11-04:

- `page_xml/<document>.page_xml.zip`: the PERO PAGE XML of the listed pages, unchanged, from
  `<library>/<document>.page_xml.zip` of the library share (`digiknihovna_public`).
- `documents.json`: per document its title, the pages in page-list order (from the Kramerius
  metadata mirror, `page_order`, #571) and the stored chunks of the shared test store whose
  text lies on these pages in the whole-document import (`id`, `order`, `fromPage`/`toPage`
  of the whole document, `text`), with the `layoutStart` that import gave them
  (`fullRunLayoutStart`). No annotations or user data.
- `scans/<document>/<page>.jpg`: two scans, converted to grayscale and downscaled to 900 px
  wide (JPEG quality 55); the page files keep the original scan's coordinates.

`generated/` is the converter's output for the sources, not edited by hand. After an intended
converter change, rewrite it from `semant_demo_backend/` with
`python -m tests.real_pages --write` and review the diff.

An excerpt is converted without the pages before it. The legacy serialization drops short
remainders depending on where chunks end, so an anchor that was exact in the whole document
can be approximate here (one chunk of the newspaper page); its position is still the same,
which `tests/test_real_pages.py` checks for every anchor.
