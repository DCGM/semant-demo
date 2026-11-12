# Collection export format

A signed-in user can export whole collections they can read (owner or member): *Export
selected* in the Collections table, or *Export* in a collection's header (#656). The export is
every annotation of each collection with the text it refers to, for annotator agreement,
backup, data analysis and datasets. It is one ZIP of JSON files. The current
`format_version` is **1**.

The KWIC export of filtered annotation rows with context (#335) is a different, later feature.

## Files

```text
semant-export-<YYYY-MM-DD>.zip
├── manifest.json
└── <name>-<id8>.json        one per collection (the full id when two would share a name)
```

### `manifest.json`

```json
{
  "format_version": 1,
  "exported_at": "2026-11-12T19:51:39.009719+00:00",
  "exported_by": {"id": "…", "name": "Olga Owner", "username": "owner"},
  "collections": [
    {"id": "…", "name": "Kroniky a dopisy", "file": "kroniky-a-dopisy-5e3a0000.json",
     "annotations": 6, "chunks": 4, "missing_chunks": 0}
  ],
  "notes": "…"
}
```

- `exported_at` is when the export started.
- The counts equal the lengths of the collection file's `annotations` and `chunks` arrays.
- `missing_chunks` counts chunks that annotations name but that no longer exist. Those
  annotations cannot be cut from the file.
- The manifest is written last. A download that stops part way is an invalid ZIP, never a
  plausible partial dataset.

### Collection file

One JSON object:

| Field | Content |
|---|---|
| `metadata` | `id`, `name`, `description`, `owner`, `created_at`, `updated_at`, `color` |
| `tags` | `id`, `name`, `shorthand`, `color`, `pictogram`, `definition`, `examples` |
| `attributes` | attribute definitions as the API returns them (`id`, `name`, `description`, `cardinality`, `all_tags`, `tag_ids`, `retired`, `revision`, `values`: `id`, `label`, `description`, `examples`, `kind` (`value` / `unknown` / `not_applicable`), `retired`) |
| `annotations` | see below |
| `chunks` | `id`, `document_id`, `order`, `text`, `in_collection` |
| `people` | `id`, `name`, `username`, `role`: `owner`, `member`, or `former` (named in an annotation's provenance but no longer a member). A deleted account has `name` and `username` `null` |

Each annotation:

| Field | Content |
|---|---|
| `id` | annotation id |
| `chunk_id`, `start`, `end` | position as stored: half-open offsets in **UTF-16 code units** from the start of the chunk's text (see below) |
| `tag_id` | a tag of `tags` |
| `type` | `pos` (approved), `neg` (rejected, kept as a negative example) or `auto` (AI suggestion not reviewed) |
| `origin` | `manual`, `ai` or `unknown` (saved before provenance was recorded) |
| `created_by`, `created_at`, `reviewed_by`, `reviewed_at`, `last_edited_by`, `last_edited_at` | provenance; user ids are in `people` |
| `ai_run_id`, `reason`, `confidence` | the AI suggestion run, and its reason and confidence |
| `edit_version` | span writes since creation |
| `revision` | boundary changes since creation (`null` before #328) |
| `attributes` | `{attribute id: [value id, …]}`, as stored. Values are accepted classifications only on approved (`pos`) annotations whose tag the attribute applies to (ADR 0011). Values kept on other annotations are exported as they are |

Annotations carry no annotated text or context: both are cut from `chunks`. Ids are
canonical lowercase UUIDs, times ISO 8601 with a time zone. Fields the store does not hold
(provenance or attributes on an older store) are `null`, `0` or `{}`.

## Positions and chunks

- `chunks` holds every chunk in the collection (`in_collection: true`).
- An annotation is stored on the chunk where it starts. `end` may exceed that chunk's
  length: the annotation then continues into the following chunks of the same document,
  consecutive by `order` (`order + 1`, `order + 2`, …), whether or not they are in the
  collection.
- Those following chunks, and chunks annotations start on that have left the collection,
  are included with `in_collection: false`. So every annotation can be cut from the file
  alone.
- Offsets count UTF-16 code units (JavaScript `String.length`). They differ from Python
  string indices only for characters outside the Basic Multilingual Plane.

Cutting an annotation in Python:

```python
import json, zipfile

def cut(annotation, chunks):
    by_id = {c["id"]: c for c in chunks}
    by_order = {(c["document_id"], c["order"]): c for c in chunks}
    anchor = by_id[annotation["chunk_id"]]
    text, order = anchor["text"], anchor["order"]
    while len(text.encode("utf-16-le")) // 2 < annotation["end"]:
        order += 1
        text += by_order[(anchor["document_id"], order)]["text"]
    units = text.encode("utf-16-le")
    return units[2 * annotation["start"]:2 * annotation["end"]].decode("utf-16-le")

archive = zipfile.ZipFile("semant-export-2026-11-12.zip")
for entry in json.loads(archive.read("manifest.json"))["collections"]:
    data = json.loads(archive.read(entry["file"]))
    for annotation in data["annotations"]:
        print(annotation["type"], cut(annotation, data["chunks"]))
```

## Consistency

The export is not a snapshot. It reads the collection while others may edit it, so an
annotation changed during the export may appear in either state. An annotation created
during the export may be missing, and one deleted may still be listed. For a consistent
dataset, export when nobody is annotating.
