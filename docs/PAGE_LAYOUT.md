# Page layout files and chunk-start anchors

The paired text/scan viewer (#351) maps canonical chunk text to OCR lines on the scan in
the frontend. It needs two things: one compact layout file per page and, per chunk, the
line where the chunk's first character is (`layoutStart`). Both are produced offline from
PERO PAGE XML by `python -m semant_demo.maintenance.page_layout` (#540); the application
never parses PAGE XML. Storage, serving and the `Chunks` field are #541; the import of the
existing corpus is #542; the frontend mapping is #544. The operator command is described in
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
- All geometry is in **integer pixels of the original scan**: `baseline` is the polyline,
  `heights` are `[above, below]` the baseline (from PERO's `custom` attribute, else
  estimated from the line polygon; null when neither exists). `wordStarts` (optional) has
  one value per word (the word rule of #463: runs of L*, M*, N*, Cf characters), the
  estimated distance along the baseline from its first point, proportional to the
  character position. Word positions are **approximate**; consumers may fall back to
  whole lines.
- Line ids are unique within a page in all PERO output seen so far; a duplicate is reported,
  and no chunk is anchored to it.

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
character. `offset` is in **UTF-16 code units** from the start of that line's transcription,
like all text offsets. Starting there and walking forward through the page files with the
separators above reproduces the chunk text for `UTF16Length(chunk.text)` units. Don't
re-trim: JavaScript `trim()` and Python `strip()` remove different characters.

`match` is:

- `exact`: the chunk text equals the regenerated text there. Every exact anchor is checked
  by replaying it. The frontend may map characters exactly.
- `approximate`: the chunk text differs from the regenerated text by at most
  `--max-edit-ratio` (default 5 %) of its length, measured with `difflib` matching blocks,
  and its first characters are found. The frontend should highlight whole lines and not
  claim character precision.

A chunk has no anchor (`layoutStart` null, with a `reason`) when it is empty, not found,
too different, ambiguous (the same text occurs more than once, or an approximate match
competes with an exact occurrence elsewhere), or would be placed before the previous
anchor. A chunk without an anchor stays fully usable as text.

Chunks are matched in `order`: first to the regenerated chunk with the same index, then at
the cursor after the previous match, then approximately in a window around it. After a
miss (for example a chunk missing from the stored list) matching resynchronizes on pieces
of the chunk that occur only once ahead. On the 13 example documents (525 pages, 2,314
chunks), all regenerated chunks anchor exactly. With perturbed copies (2 % edits,
collapsed whitespace, 20 % insertions, a missing chunk every ten) and with a wrong page
order, every anchor produced pointed to the right line and offset; heavily edited or
misordered chunks got none.
