# Page layout files and chunk-start anchors

The paired text/scan viewer (#351) maps canonical chunk text to OCR lines on the scan in
the frontend. It needs two things: one compact layout file per page and, per chunk, the
line where the chunk's first character is (`layoutStart`). Both are produced offline from
PERO PAGE XML by `python -m semant_demo.maintenance.page_layout` (#540); the application
never parses PAGE XML. Storage, serving and the `Chunks` field are #541
([below](#page-asset-store-and-reads-541)); the import of the existing corpus is #542; the frontend mapping is #544
([below](#textscan-correspondence-544)); the workspace is #545. Its validation on real OCR
material, with the measured coverage and the known approximations, is
[below](#validation-on-real-material-546) (#546). The operator command is described in
[DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#page-layout-files-and-anchors-page_layout-540).

## Page file (`semant.page-layout`, version 1)

The first line of a page of the example document `0004077e…` (abridged to one region):

```json
{"schema": "semant.page-layout", "version": 1, "pageId": "4a2c533a-aa49-11e3-9f73-d485646517a0",
 "params": {"lineConfidence": 0.6, "minChunkChars": 768, "maxChunkChars": 1152},
 "image": {"width": 1378, "height": 2000},
 "regions": [{"id": "r004", "lines": [{"id": "r004-l003", "text": "Ročník XIX.",
   "baseline": [[100, 158], [124, 158], [146, 157], [166, 157], [187, 157], [207, 157], [229, 157], [255, 157]],
   "heights": [19, 7], "wordStarts": [0, 99]}]}]}
```

- One file for every page of the document's page list, including covers, blank pages and
  pages without PAGE XML (`image` null, no regions).
- `pageId` is the metadata page UUID (from the `page_order` export, #571), not PERO's
  `imageFilename`.
- `params` are the chunking parameters the file was made with. The lines in a file depend
  on them, so files and anchors are always regenerated together.
- `regions` and their `lines` are in serialization order and contain **only the lines that
  contribute to canonical text**: lines below the confidence threshold, empty lines and
  dropped short paragraphs are left out. A region with no such line is left out.
- `text` is the PAGE XML transcription verbatim (no trimming, no dehyphenation).
- All geometry is in **integer pixels of the scan**: the converter writes the original scan's
  (PAGE XML) pixels; the asset store's files are scaled to its stored, derived scan (#594,
  [DATA_MAINTENANCE](DATA_MAINTENANCE.md#page-scans-layouts-and-anchors-for-the-existing-corpus-page_import-542)),
  so `image` is always the size of the JPEG served with it. `baseline` is the polyline,
  `heights` are `[above, below]` the baseline (from PERO's `custom` attribute, else
  estimated from the line polygon; null when neither exists). `wordStarts` (optional) has
  one value per word (the word rule of #463: runs of L*, M*, N*, Cf characters), the
  estimated distance along the baseline from its first point, proportional to the
  character position. Word positions are **approximate**; consumers may fall back to
  whole lines.
- Line ids are unique within a page in all PERO output seen so far; a duplicate or a missing
  id is reported, and no chunk is anchored to such a line (`duplicate_line_id`,
  `missing_line_id`).

## Serialization (the legacy chunking)

The corpus chunks were made by `db_benchmarks/semant/prepare_documents.py` /
`db_prepare_documents.py`. The converter reproduces their loop exactly
(`page_layout/serialize.py`, tested against a literal port):

1. Pages in page-list order. A page without PAGE XML is skipped. A malformed page made the
   legacy code fail the whole document (no chunks), and so does the converter.
2. Regions in **XML element order** (pero-ocr reads `ReadingOrder` but did not apply it);
   lines in XML order; lines without a `Baseline` are dropped.
3. A line is kept when it has text and `conf > lineConfidence`.
4. A region's paragraph is its kept lines joined with `\n`; a paragraph (or the rest of a
   split one) of at most 10 code points is dropped.
5. A paragraph that fits is appended as `\n\n` + paragraph and closes the chunk when the
   chunk length before it plus the paragraph length exceeds `minChunkChars`. One that would
   exceed `maxChunkChars` adds `\n`, then `\n` + line, line by line, until the chunk has
   `minChunkChars`; the rest goes to a new chunk.
6. A trailing empty chunk is dropped; every chunk is `str.strip()`-ped. Lengths count code
   points.

Document text is the chunks concatenated without separators (#463). So a non-empty chunk
always starts on a line character, never on a separator. **Inside a chunk, lines are
separated by `\n` within a region and `\n\n` between regions and pages.** That is the
whole contract the frontend needs to walk the page files.

## `layoutStart`

`layoutStart = {pageId, lineId, offset, match}` gives the line holding a chunk's first
character. Each line of `anchors.jsonl` also carries the `params` and `maxEditRatio` it was
made with; an anchor is valid only with page files of the same `params`. `offset` is in **UTF-16 code units** from the start of that line's transcription,
like all text offsets. Starting there and walking forward through the page files with the
separators above reproduces the chunk text for `UTF16Length(chunk.text)` units. Don't
re-trim: JavaScript `trim()` and Python `strip()` remove different characters.

`match` is:

- `exact`: the chunk text equals the regenerated text there. Every exact anchor is checked
  by replaying it. The frontend may map characters exactly.
- `approximate`: the Levenshtein distance (unit insertions, deletions and substitutions; a
  transposition counts 2) between the chunk text and the best-aligned regenerated text is
  at most `--max-edit-ratio` (default 5 %) of the chunk's length, and its first characters
  are found. `differences` is that distance. The frontend should highlight whole lines and
  not claim character precision.

A chunk has no anchor (`layoutStart` null, with a `reason`) when it is empty, not found,
too different, ambiguous (the same text occurs more than once with nothing to tell the
copies apart, or an approximate match competes with an exact occurrence elsewhere), starts
on a line without a usable id, or would be placed before the previous anchor. A chunk
without an anchor stays fully usable as text.

Chunks are matched in `order`, never before the previous anchor. Position is evidence only
for a *contiguous* chunk, one whose `order` directly follows the last anchored chunk (or
order 0 at the start): it is matched at the cursor after that match, or uniquely near it,
then approximately in a window around it. After a gap (stored chunks missing, including the
first ones, or an unanchored chunk) the text must occur exactly once after the previous
anchor, or match approximately near pieces of it that occur only once ahead. A stored
`order` is never used as an index into the regenerated chunks: identical text (for example
repeated pages) after a gap gets no anchor rather than one on the wrong copy. On the 13 example documents (525 pages, 2,314
chunks), all regenerated chunks anchor exactly. With perturbed copies (2 % edits,
collapsed whitespace, 20 % insertions, a missing chunk every ten) and with a wrong page
order, every anchor produced pointed to the right line and offset (1,396 exact and 458
approximate of 2,088 perturbed; 1,299 and 321 with a wrong page order); heavily edited or
misordered chunks got none.

## Page asset store and reads (#541)

The application serves the page files, the scans and thumbnails from one directory,
`PAGE_ASSETS_DIR` (empty: no document has pages). It only reads it; the existing-corpus
import (#542, [DATA_MAINTENANCE](DATA_MAINTENANCE.md#page-scans-layouts-and-anchors-for-the-existing-corpus-page_import-542))
writes it, together with an anchor plan (`anchors.jsonl`, never served) per document. Every path is derived from UUIDs, never from client text
(`adapters/filesystem/page_assets.py`):

```text
<root>/<first two hex digits of the document id>/<document id>/manifest.json
<root>/<..>/<document id>/<page id>.jpg          the scan, a JPEG derived from the original (#594)
<root>/<..>/<document id>/<page id>.json         the page file above
<root>/<..>/<document id>/<page id>.thumb.jpg    the thumbnail
```

A file whose real location is outside the root (a symbolic link leaving it) or that is not a
regular file counts as absent. Files are replaced atomically (written next to the target,
then renamed); there is no transaction across files and no backup: the assets can be
regenerated.

The **manifest** (`semant.page-manifest`, version 1) lists every page of the document's page
list (`page_order`, #571) in order, covers, blanks and pages without assets included:

```json
{"schema": "semant.page-manifest", "version": 1, "documentId": "<uuid>", "library": "nlk",
 "params": {"lineConfidence": 0.6, "minChunkChars": 768, "maxChunkChars": 1152},
 "pages": [{"pageId": "<uuid>", "order": 0, "label": "[1]", "pageType": "FrontCover",
            "width": 1378, "height": 2000, "image": true, "layout": true, "thumbnail": true}]}
```

`order` is the page's index in the list (0, 1, ...), the page number of the chunks'
`from_page`/`to_page`. `params` are those of the page files, so they match the chunks'
anchors. `image`/`layout`/`thumbnail` say which assets are stored. A manifest that does not
parse, has duplicate pages, orders other than 0, 1, ... or another document's id is
treated as absent (and logged).

**Reads** (public, like the document text; each first checks that the document exists, the
one place where a future access rule, #279, applies):

- `GET /api/documents/{document_id}/pages`: `DocumentPages`, the pages with the URL of each
  available asset (`image_url`, `layout_url`, `thumbnail_url`). Without a manifest,
  `available` is false and `pages` empty: a text-only document. `Cache-Control: no-cache`.
- `GET /api/documents/{document_id}/pages/{page_id}/{image|layout|thumbnail}`: the file
  (`image/jpeg` or `application/json`), 404 when absent. Scans and thumbnails are cached for
  a day; layout files are revalidated (`no-cache`), since a re-import with other parameters
  replaces them together with the anchors. All carry an `ETag` and answer `If-None-Match`
  with 304.
- `GET /api/documents/{document_id}/chunks/by_page?page=N&limit=20` (at most 50):
  `PageChunks`, the chunks whose `from_page`..`to_page` includes page `N`, in document
  order, with `has_more`. It opens a page directly without reading earlier pages. The page
  ranges are the stored, coarse ones: in a sample of the corpus a chunk starting at the top
  of a page often names the previous page as `from_page`/`start_page_id`, so the result can
  include one chunk too many, never one too few. `layoutStart` is the exact start.

Clients use only the URLs of the manifest, so the storage can change behind them.
`layoutStart` is returned on `DocumentChunk` (document view, passage reads, Search hits,
page chunks) and `CollectionChunk`; chunks without it are text-only.

## Scan viewer (#543)

`DocumentImagePane` (`semant_demo_frontend/src/features/documents/scan/`) is the scan half of
the document workspace: one whole page at a time, its OCR lines as an overlay, page
navigation and a thumbnail strip. It reads the manifest and, for the current page only, the
layout file (at most 24 parsed layouts are kept; a page left before its layout arrives cancels
the request and never shows its lines). It knows nothing of the text: line clicks and
keyboard focus are reported as `{pageId, lineId, offset?}` (the source ids of the page file;
`offset` is the UTF-16 start of the word clicked, estimated from `wordStarts`), and highlights
and focus requests come in the same terms. The correspondence with chunks and annotations
is #544 ([below](#textscan-correspondence-544)).

- **Geometry** (`pageLayout.ts`): a line is the band from `heights[0]` above to `heights[1]`
  below its baseline, perpendicular to each baseline segment, so skewed and curved lines are
  followed. A line without heights takes the page's median. Word starts are used only when
  their number equals the words of the text by the #463 rule (`\p{L}\p{M}\p{N}\p{Cf}` runs);
  otherwise the line is used as a whole. A highlight of a text range covers whole
  (approximate) words, never character positions.
- **One coordinate system** (`viewport.ts`): the scan and the overlay are drawn in scan
  pixels inside one element moved by one transform, so they stay aligned under zoom, pan, fit,
  resize and page changes. A fitted page is fitted again on resize; a zoomed one keeps the
  point at the viewer's center.
- **Smart focus** moves the page only when the target is not fully inside the viewer with a
  24 px margin, by the least distance, and zooms in only when a line is shown under 10 px high
  (to about 22 px, no further than the line still fits across); it never zooms out.
- **Keys** while the pane has focus: Up/Down previous/next line, PageUp/PageDown previous/next
  page, +/− zoom, 0 fit. Tab and Shift+Tab move focus as usual; keys typed into a field
  (the page field) and modified keys are left alone.
- **Missing parts**: a document without a manifest is text only; a page without a scan says so;
  a scan without a layout (or a layout that fails to load, with Retry) is shown without lines.

In the application the pane is a part of the document workspace (#545, below). On its own it
has a preview page, `/#/preview/scan/<document id>?page=<page id>`, the harness of its browser
tests, built only with `SEMANT_PREVIEW_ROUTES=1` (the dev server and the browser-test builds).
The browser-test profile and the local development backend serve synthetic page fixtures
(`tests/page_fixtures.py`).

## Text/scan correspondence (#544)

`semant_demo_frontend/src/features/documents/correspondence/` connects the text pane (#539)
and the scan viewer (#543) in the browser. Nothing about it is stored: no line-to-chunk table,
no per-line text ranges, no matching service.

- **The walk** (`layoutMap.ts`) is the importer's `replay`: from a chunk's `layoutStart`, the
  rest of the anchor line from `offset`, then each following line of the page files, preceded by
  `\n` within a region and `\n\n` between regions and pages, for the chunk's length in UTF-16
  units. It reads the anchor's page and only the following pages the chunk reaches, through the
  scan viewer's layout cache. The result is the chunk's *pieces*: for each line, the same
  text's `[start, end)` in the line and in the chunk; the separators lie between them.
- **Precision.** A map is `exact` only when the anchor is `exact`, the walk reproduces every
  character and separator of the chunk text and no page file on the way has malformed lines.
  Otherwise it is `approximate`: only whole lines are shown, on the scan (dashed highlight) and
  in the text (dashed passage, a `≈` page mark at the nearest word start), with a notice. A walk
  that reaches a page without a layout file stops there; the rest of the chunk is text only.
  A chunk without an anchor, or whose anchor's page or line is not in the files, has no map.
- **Text to scan.** A click in the text highlights the line of the caret (and its word, from
  `wordStarts`, when exact) and marks that line's text; a selection highlights every line of
  every page it covers, across chunks, and the scan viewer focuses its beginning only.
- **Scan to text.** A click or keyboard step on a line marks the line's text (an exact map
  maps the word clicked to its character) and reveals it. The candidate chunks are the ones
  shown whose `from_page`..`to_page` includes the page, then `chunks/by_page` for that page.
- **Pages.** Page navigation in the scan viewer brings the page's first text into view,
  reading `chunks/by_page` for that page alone; a page without line positions falls back to the
  chunk whose stored range covers it. The text marks where each page's text begins (an
  element outside the text: not selected or copied, offsets unchanged) and tints the part on
  the page shown, for the chunks near that page.
- **Smart focus, no feedback.** Only explicit interactions move the other pane: a click or
  selection, a line step, page navigation, a deep link. Scrolling, zooming and panning are never
  followed; the text scrolls only when its target is not visible with a margin, the scan
  viewer as in #543. A focus request's own page change is not followed back. A newer
  interaction, or scrolling the text, cancels a pending one, so a late layout or page read
  never moves a pane afterwards.
- **Bounded text** (`useDocumentText`): the chunks around a deep-linked chunk (`/window`), of an
  opened page (`/by_page`), extended with `/adjacent` on request; never all earlier pages or the
  whole document.

The browser-test profile and the local development backend store anchors for the fixture
chunks (`fixture_anchors` in `tests/page_fixtures.py`; verified against `replay` by
`tests/test_page_fixtures.py`).

## Document workspace (#545)

`semant_demo_frontend/src/features/documents/workspace/` puts the text and the scan viewer
side by side in the application, in two places that share the components and the
correspondence but not their text:

- **The public document view**, `/#/documents/<document id>` (`PublicDocumentPage`, no sign-in):
  the bounded public text (`useDocumentText`), read-only, no collection and no annotation read,
  the document's metadata in the general right sidebar (*Document*). `?page=<page id>` opens a
  page and its text, `?chunk=<chunk id>&start=&end=` a passage (UTF-16 offsets in the chunk) and
  its lines, `?view=split|text|scan` the view, `?from=search|chat` the back link. Search
  results and chat sources open it from their context panel (*Open document*), which stays the
  light, in-page view of a passage.
- **The collection's document view**, `/#/collections/<cid>/documents/<did>/v1`: the reader with
  its annotations, gutters and tools unchanged, the scan beside it (`useReaderScanSync`). A page
  opened in the scan is found in the reader's text by reading that page's chunks
  (`pageChunks.ts`: `/chunks/by_page`, continued with `/adjacent`) and showing only their orders
  in the reader (`useChunkWindow.showRange`, with their annotations), leaving a gap to the text
  shown rather than loading everything in between. As on the initial load (`preloadGapChunks`),
  a gap it opens of at most `GAP_PRELOAD_LIMIT` (100) chunks is read as hidden chunks, so
  annotations crossing it are shown and edited across it; a larger gap is not read, and an
  annotation running into it is reported in the gap's row (*An annotation continues in the
  missing text*, `useAnnotations.cutAtGapOrders`) rather than cut silently. The initial load
  still shows all the collection's chunks of the document. Clicks and selections in the text, an
  annotation link (`?annotation=`), a chunk link (`?chunk=&order=`), a page link (`?page=`) and
  summary or chat citations show their lines on the scan; the annotation popover works as
  before. A collection the user cannot read says so and links to the public view.
- **Layout** (#600). Both views fill the window under the application header and do not
  scroll as a page: a one-row header (`DocumentHeader`: back link, title cut with an ellipsis
  and whole in its tooltip, subtitle or byline, *Original*, and the collection in the
  collection view), a fixed controls row (`WorkspaceControls`: the whitespace toggle, in the
  collection view with the rest of the reader's tools; the synchronization notice; the view
  toggle) and the workspace (`DocumentWorkspace`). The workspace shows the scan on the left
  and the text on the right; the text scrolls in its own pane, the scan keeps its page
  controls and thumbnails in view and is panned and zoomed on its own. The divider between
  them is dragged or moved with the arrow keys (Shift: larger steps; Home/End: the text's
  smallest and largest width; a double click resets it); the text starts at 55 %, both panes
  keep a minimum width (`splitRatio.ts`), and the split is remembered in this browser. A
  document without scans is text only, without a choice of views; otherwise *Scan*, *Text
  and scan* or *Text* (`WorkspaceModeToggle`), and only one of them when the workspace is
  under 720 px wide. The scan viewer stays mounted while hidden, so it keeps its page;
  showing the text again reveals the passage last focused from the scan.
- **Links.** The link's target (a passage, an annotation or chunk, a page) and its view are
  followed also when only the query changes (another link to the same document: the page is
  reused, the document is not read again). The reader's own page changes in the scan viewer
  (page buttons and keys, thumbnails, the page field: the pane's `navigate` event) are written
  into the URL as `?page=`, replacing the target they supersede (`chunk`/`start`/`end`, or
  `annotation`/`chunk`/`order`), so a reload opens the page the reader moved to. The first page
  and pages opened for the text (a click, a selection, a linked target) leave the link as it was.
  In the collection view the scan's page is followed in the text only once the reader's text
  is loaded, and only the latest page shown meanwhile.
- **Return.** Search and Chat are kept alive while another page is shown (`router/keptPages.ts`,
  `meta.keepAlive`; their sidebar panels leave and return with them and their window listeners
  pause, `shared/whileShown.ts`), so the back link or browser back finds the results, the
  opened result or source and the scroll position as they were. The state is in memory: after
  a reload of the document the back link leads to an empty search or conversation. This part
  of #545's reload criterion is deferred, tracked in #584.

## Validation on real material (#546)

The whole chain was run on real data: the 32 documents of the shared test store (3,260 stored
legacy chunks, 1,565 pages; page lists from the metadata mirror, PERO PAGE XML and scans from
the library share), read-only there, written only to a disposable copy. Run records are on
#546; this section keeps the contracts and the numbers to expect.

**Coverage.**

| | Chunks | |
| --- | --- | --- |
| Exact anchor (character-precise map) | 2,886 | 88.5 % |
| Approximate anchor (whole lines) | 80 | 2.5 % |
| No anchor (text only) | 294 | 9.0 % |

26 of the 32 documents anchor every chunk exactly. Nearly all misses are in six documents whose
stored chunks are not made from the PAGE XML that exists now: another OCR version, legacy page
lists that repeat pages (the copies get no anchor, as intended), pages without PAGE XML
(#591). The browser walk (`layoutMap.ts`) maps all 2,886 exact anchors exactly, rebuilding
each stored text from line pieces and separators (2.4 million UTF-16 units, no difference),
and all 80 approximate ones as approximate. All 1,617 stored annotations and legacy spans on
anchored chunks resolve to scan lines (301 over several lines, 6 over two pages).

**Precision, separately from the text mapping.** Text offsets are exact wherever an anchor is
exact; positions *within* a line are estimates. Word starts (`wordStarts`) are usable on
99.6 % of the lines (the rest are highlighted as whole lines). Compared with PERO's own word
boxes (ALTO `String/@HPOS` of the 13 example documents, 254,000 words), an estimated word
start is off by a median of 7 px (p90 23 px, p99 46 px), 0.07 of the line's mean word pitch;
99.6 % are within half a word. So a highlight covers whole, approximately placed words, never
claimed character positions.

**Known limitations.**

- The stored page fields are coarse: a chunk at the top of a page often names the previous page
  as `from_page` (179 of 2,966 anchored chunks here). The viewer uses `layoutStart`, not the
  page fields, for positions; `by_page` reads may return one chunk too many.
- A chunk whose text changed after the import keeps its old anchor until `page_import assets`
  runs again; it is then shown as approximate (#593).
- The legacy serialization of a page depends on the pages before it (short remainders are
  dropped depending on where chunks end), so page files and anchors are made from the whole
  document only. Converting an excerpt of pages can turn exact anchors into approximate ones at
  the same position; the real-page fixtures show this on purpose.
- Pages that are not mounted on the import machine get no scan (`missing_image`); the viewer
  says so and the text and lines still work.
- Rapid paging still downloads each passed page's scan in full (#592).

**Import behaviour.** On the disposable copy, `assets` killed in the middle of a document left
only whole files and no manifest (the document stays text-only); running it again skipped the
finished pages and produced a tree byte-identical to an uninterrupted run. `anchors --write`
killed after 443 writes was completed by running it again (2,523 more, then `--check` exit
0). Before and after, every object of the store (6,670) had the same id, properties
(chunk text, order, page fields, references, annotation offsets) and vectors; only
`Chunks.layoutStart` differed, on the 2,966 anchored chunks.

**Browser.** On the real 182- and 528-page documents, opening a page reads its manifest
(88 KB and 116 KB), that page's chunks, the layouts of the page and its neighbours and the
visible thumbnails, nothing else of the document (JS heap 10–15 MB). Twelve page steps within
154 ms abort all twelve stale layout reads and end on the right page and `?page=`.

**Regression fixtures** (`semant_demo_backend/tests/real_pages.py`): excerpts of five of these
documents (1839–1922) in `tests/fixtures/real_pages/`, with their stored chunk texts and the
anchors of the whole-document import: a whole 1839 newspaper page; a 1913 newspaper page in
columns with the most curved and skewed baselines; the first sixteen pages of a 1906 volume,
where one chunk crosses ten page breaks, blank pages, OCR of bleed-through below the
confidence threshold and a caption repeated on three pages, and later chunks cross page
breaks; a page whose legacy chunks repeat it; chunks from another OCR. `generated/` is the
converter's output for them, checked by `tests/test_real_pages.py` and read by the frontend's
`realPages.spec.ts` (the walk in both directions, hyphenated words, cross-page chunks); two
downscaled scans serve `test/e2e/realScans.spec.ts`. It checks on the 1906 text page that the
line bands lie on their printed lines (each band's darkest position within 0.2 of a band of
where it is drawn, for more than 70 % of the bands; 93 % measured, 0–17 % for bands drawn 0.4
of a band off) after zoom, pan, wheel zoom, resize and at phone width, and on the newspaper,
whose small print and ruled boxes make that measure ambiguous, that the most curved and skewed
bands follow their baselines on a scan smaller than the one the geometry refers to. The real
corpus has no non-BMP text; the synthetic fixtures keep covering it.
