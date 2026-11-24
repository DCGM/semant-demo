# Appended-data fixture (#798)

`chunks.jsonl` is the input of the tests over appended data (`tests/append_pipeline.py`, used by
`tests/integration/test_append_pipeline.py` and `test_import_status.py`): chunk lines in the
format of `chunk_ingest`, appended to the seeded fixture corpus.

| Document | Lines | Taken from |
| --- | --- | --- |
| `000b03e0-…` *Karlínské listy* (Czech) | orders 24–26 | `real_pages/documents.json` |
| `00246353-…` *Freudenthaler Zeitung* (German) | orders 0–1 | `real_pages/documents.json` |
| the seeded `chronicle` | orders 3–4 | written for this test |

Derived on 2026-11-20 from [`../real_pages/documents.json`](../real_pages/documents.json)
(#546), a copy so that a change of that page-layout fixture (#351) does not change this test:

- `id`, `order` and `text` as stored; `document` from `documentId`; `from_page`/`to_page` from
  `fromPage`/`toPage`; `start_page_id` is the `pageId` of the chunk's first page
  (`pages[sourcePageOrders.index(fromPage)]`); `fullRunLayoutStart` is left out.
- `language` is not in the source: `ces` for *Karlínské listy*, `deu` for the *Freudenthaler Zeitung*.
- `end_paragraph` is not in the source either: `true` on every line, as the import data of the
  corpus always carry it, except the second *Karlínské listy* line, which the test reads without
  it.
