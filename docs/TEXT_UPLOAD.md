# Uploading private text documents (#785)

The owner of a collection can upload plain-text files into it: **Upload text documents** in
the collection's *Documents & tagging* tab, next to *Add from Library*. Each file becomes a
new, **private** document (`Documents.public = false`) of that collection, with ordered,
embedded chunks. It is readable only through the collection, by its owner and the users it
is shared with ([ADR 0007](adr/0007-access-and-collaboration.md#corpus-document-rights-279-decided-2026-11-18),
#279), and never appears in unscoped Search, Explore, RAG, MCP or corpus counts.

The upload is the API route `POST /api/user_collections/{collection_id}/text_documents`
(`multipart/form-data`: `files`, one or more; `metadata`, optional). Code:
`features/user_collections/text_upload.py` (validation, chunking, embedding, write order),
`adapters/weaviate/text_upload.py` (the writes and readbacks), frontend
`features/documents/upload/`.

## Files

- `.txt` files of UTF-8 plain text; an initial byte order mark is dropped, `\r\n` and `\r`
  line ends become `\n`. Other encodings, binary content (a NUL character) and empty files
  are refused.
- The title is the file name without `.txt` unless the CSV gives one. The file name is not an
  identifier: every upload creates a new document with new ids, also for a name uploaded
  before. Two files of one upload may not have the same name.
- No library code, Kramerius URL, page ids or scans are invented; the document is text-only
  and its chunks have no `start_page_id`, `from_page` or `to_page`.

Limits (backend, `UploadLimits`; the client checks the first ones too): 20 files per
upload, 2 MB per file, 1 MB for the CSV, 24 MB per request, 2,000 chunks per file, and two
uploads at a time per backend process (another answers 503 before its files are read), so
uploads leave the embedder room for search queries. Files are processed one after another;
a large upload takes minutes (it is one request: keep the dialog open).

## Metadata CSV

Optional. UTF-8 (a byte order mark is allowed), comma separated, with a header row.
Copy this template (also offered for download in the dialog):

```csv
filename,title,author,yearIssued,language,description
example.txt,Example document,Jane Doe,1925,cs,Optional description
```

| Column | Required | Stored as |
| --- | --- | --- |
| `filename` | yes | Matches exactly one uploaded file name (case-sensitive, as uploaded). Not stored. |
| `title` | no | `Documents.title`; blank: the file name without `.txt`. At most 500 characters. |
| `author` | no | `Documents.author`, a one-element list. At most 300 characters. |
| `yearIssued` | no | `Documents.yearIssued` (an integer, e.g. `1925` or `-50`) and the chunks' copy `Chunks.yearIssued` used by year filters (#153). |
| `language` | no | `Documents.language` and `Chunks.language`. At most 32 characters. |
| `description` | no | `Documents.description`. At most 5,000 characters. |

Any other column (`public`, `library`, `id`, ...) refuses the upload: the CSV cannot set
rights, the source library or ids. Files without a row get only their title. Kramerius
`metadata_sync` is never run for these documents.

Every problem is reported before anything is written, and **any problem means nothing of the
upload is saved**: the file's own problem (encoding, size, its CSV row's year or length) on
that file (`invalid`), the others marked `not_written`; problems of the CSV as a whole
(encoding, header, unknown or repeated columns, rows naming files that are not uploaded) in
the response's `errors`.

## Chunks and embeddings

The text is cut into paragraphs at blank lines; whole paragraphs are packed into chunks of
up to 1,000 characters, and a paragraph longer than 1,500 is split at whitespace
(`chunk_text`, deterministic). The chunk texts joined in order are exactly the file's text
(paragraph breaks included), so positions (`startChar`, `startWord`, `wordOpenAtStart`,
computed by `features/documents/positions.py`, #463) and annotation offsets refer to that
text. `end_paragraph` marks a chunk that ends a paragraph. Every chunk gets
`classification_provenance = UNPROCESSED` (#590) and, where the store declares them,
`documentPublic = false` (#793; the document is private) and `haveVector` listing the vectors
written (#805; no embedder selects the chunk again). No classification, title generation or
chunk summaries run during an upload (below).

Each chunk gets a vector for **every configured search vector** (`SEARCH_VECTORS_CONFIG`),
computed with that vector's document-side embedding (`embed_documents`, the plain chunk
text for the Qwen vector, as `data_tools/embedder` writes it), in batches of 32 with up to
3 attempts per batch. An upload is refused (503) unless every configured vector is marked
`private_text: true`: only a self-hosted model on infrastructure the deployment controls
may receive private text. The shipped Qwen and Gemma configurations are self-hosted and
marked; a configuration that adds an external embedding provider disables uploads until
that is decided.

The store must declare what the upload writes (`Documents.title`, `public`, the
`collection` reference; `Chunks.text`, `order`, `end_paragraph`, the position properties,
`classification_provenance`, the `document` and collection references and every configured
named vector; `documentPublic` and `haveVector` are optional but must have their documented
types when declared); otherwise uploads answer 503 and the server log names what is missing. The
schema is never changed by an upload.

## Write order and results

Access (owner only; a shared user gets 403, others 404, signed out 401) and the
configuration are checked before the request body is read. Then, per file:

1. the document is inserted, private and **not linked** to any collection;
2. its chunks are inserted batch by batch as they are embedded, each with its document and
   collection references and its vectors in one write;
3. everything is read back: every chunk with its order, text, references and vectors, and no
   other chunk of the document;
4. the document is linked to the collection. Only from now on can anyone read it.

Each file's result (`TextUploadFileResult`):

| Status | Meaning | What to do |
| --- | --- | --- |
| `completed` | Saved, read back and in the collection. | — |
| `invalid` | The file or its CSV row is invalid (`error`). Nothing of the upload was saved. | Correct or remove it and upload again. |
| `not_written` | Valid, but not saved because of another problem of the upload. | Upload again once that is corrected. |
| `failed` | Saving stopped (`error`: the step, e.g. an embedding outage). The document is in no collection and nobody can read it. | Upload the file again: it becomes a new document. |
| `uncertain` | Saved, but adding it to the collection could not be confirmed. | Reload the collection; upload again only if the document is missing. |

The dialog keeps the files that were not saved selected and removes saved ones, so uploading
again never creates a second copy; after a partial success it also clears the CSV (it names
saved files too, which a new upload would refuse) and asks for one with the remaining rows.

Nothing is rolled back or deleted (ADR 0002). A failed or interrupted upload leaves a private
document, possibly with some chunks, that belongs to no collection. No reader shows it:
unscoped reads need `public = true` and collection reads need the link. It is never reused.
Its chunks carry the collection reference, so the collection's raw chunk count
(`/stats`) includes them until they are removed. The server logs the document id with
`Text upload: document <id> stopped at <step>`.

## Operations

**Finding leftovers of failed uploads.** Documents with `public = false` and no
`collection` reference are either leftovers of failed uploads or documents removed from
every collection that held them (or whose collections were deleted). They are unreachable:
nobody can read them, so nobody can add them to a collection again (#279). An owner can add
an uploaded document to another collection of theirs while it is still readable through the
first one. A
removal command is not part of #785 (see [TODO.md](TODO.md)); `document_cleanup` removes
only documents without chunks.

**Downstream processing.** Uploaded chunks are found by `classification_provenance =
UNPROCESSED` together with their document's `public = false`. Their text must reach only
models approved for private text:

- `data_tools/meta_data_enrichment` (classification) selects chunks of documents that are
  not public only for a local model, or with `include_restricted_documents: true`
  ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#chunk-classification-data_toolsmeta_data_enrichment-590)).
- `chunk_titles` defers them (`deferred_restricted_document`) unless
  `--include-restricted-documents`
  ([DATA_MAINTENANCE.md](DATA_MAINTENANCE.md#chunk-titles-chunk_titles-575)).
- `chunk_summaries` makes no model call; its corpus-wide pass is not needed for an upload, so
  the new documents match no chunk-value document filter until its next scheduled run.
- `metadata_sync`, `page_order` and `page_import` do not apply: the documents have no library
  and no pages.
