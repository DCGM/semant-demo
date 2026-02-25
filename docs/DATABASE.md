# Database Schema

The application uses two databases:

1. **Weaviate** — primary vector + document store (collections, references, HNSW index)
2. **SQLite** — lightweight task-tracking for async tagging jobs

---

## Weaviate Schema

```mermaid
erDiagram
    Documents {
        uuid id PK
        text library
        text title
        text subTitle
        int partNumber
        text partName
        int yearIssued
        date dateIssued
        text_array authors
        text publisher
        text description
        text url
        bool public
        text documentType
        text_array keywords
        text genre
        text placeTerm
        text section
        text region
        text id_code
        text seriesName
        int seriesNumber
        text edition
        text manufacturePublisher
        text manufacturePlaceTerm
        text_array illustrators
        text_array translators
        text_array editors
        text_array redaktors
    }

    Chunks {
        uuid id PK
        text text
        vector embedding
        text start_page_id
        int from_page
        int to_page
        bool end_paragraph
        text language
        text_array ner_P "Person"
        text_array ner_T "Temporal"
        text_array ner_A "Address"
        text_array ner_G "Geographical"
        text_array ner_I "Institution"
        text_array ner_M "Media"
        text_array ner_N "Unknown - legacy"
        text_array ner_O "Cultural artifact"
    }

    Tag {
        uuid id PK
        text tag_name
        text tag_shorthand
        text tag_color
        text tag_pictogram
        text tag_definition
        text_array tag_examples
        text collection_name
    }

    UserCollection {
        uuid id PK
        text name
        text user_id
    }

    Chunks ||--|| Documents : "document (1:1)"
    Chunks }o--o{ Tag : "automaticTag (many:many)"
    Chunks }o--o{ Tag : "positiveTag (many:many)"
    Chunks }o--o{ Tag : "negativeTag (many:many)"
    Chunks }o--o{ UserCollection : "userCollection (many:many)"
    Tag }o--o{ UserCollection : "userCollection (many:many)"
```

### Collection: `Documents`

Stores bibliographic metadata for each digitised document (book, periodical issue, etc.). No vector index — documents are not directly searchable by similarity.

Key fields:
- `library` — source digital library identifier (e.g. `"mzk"`)
- `yearIssued` / `dateIssued` — used for temporal filtering
- `authors` — array of author names
- `documentType`, `genre`, `keywords` — categorical metadata
- `url` — link back to the source digital library page
- `public` — whether the document is publicly accessible

### Collection: `Chunks`

The core searchable collection. Each chunk is a contiguous text block (typically paragraph-level, may span pages) with:

- **HNSW vector index** — pre-computed embeddings from `BAAI/bge-multilingual-gemma2`
- `text` — the full chunk text (also used for BM25)
- `from_page` / `to_page` — page range in the source document
- `start_page_id` — UUID of the first page
- `ner_*` — named entity arrays extracted by NER (Persons, Temporal, Address, Geographical, Institution, Media, Cultural artifacts)

#### References from Chunks

| Reference | Target | Cardinality | Description |
|---|---|---|---|
| `document` | Documents | 1 | Parent document |
| `automaticTag` | Tag | many | Tags assigned by LLM |
| `positiveTag` | Tag | many | Tags approved by user |
| `negativeTag` | Tag | many | Tags rejected by user |
| `userCollection` | UserCollection | many | User collections containing this chunk |

### Collection: `Tag`

User-defined tags with:
- `tag_name`, `tag_shorthand` — display name and abbreviation
- `tag_color`, `tag_pictogram` — UI presentation
- `tag_definition` — text description used by LLM for tagging
- `tag_examples` — example texts (used in LLM prompt)
- `collection_name` — the Weaviate chunk collection this tag was created for

### Collection: `UserCollection`

Named collections of chunks per user:
- `name` — user-provided collection name
- `user_id` — owner identifier

---

## SQLite Schema (Task Tracking)

A single `tasks` table tracks asynchronous tagging jobs:

```sql
CREATE TABLE tasks (
    taskId          VARCHAR(36)  PRIMARY KEY,   -- UUID
    status          VARCHAR(20)  DEFAULT 'PENDING',  -- PENDING | RUNNING | COMPLETED | FAILED
    result          JSON,                        -- final result or error
    all_texts_count INTEGER,                     -- total chunks to process
    processed_count INTEGER,                     -- chunks processed so far
    collection_name VARCHAR,                     -- target chunk collection
    tag_id          VARCHAR(36),                 -- UUID of the tag being applied
    tag_processing_data JSON,                    -- per-chunk tagging details
    time_updated    DATETIME,                    -- auto-updated timestamp
    task_name       VARCHAR                      -- asyncio task name (for cancellation)
);
```

Task lifecycle: `PENDING` → `RUNNING` → `COMPLETED` / `FAILED`

The backend polls this table via `GET /api/tag_status/{taskId}` and the frontend uses periodic polling to display progress.

---

## Data Ingestion

Data is loaded using `weaviate_utils/db_insert_jsonl.py`:

```bash
python db_insert_jsonl.py \
    --source-dir /path/to/data \
    --delete-old \
    --document-collection Documents \
    --chunk-collection Chunks \
    --tag-collection Tag \
    --usercollection-collection UserCollection
```

Expected input directory structure:
```
source-dir/
├── *.json          # one JSON per document (bibliographic metadata)
├── *.jsonl         # one JSONL per document (one line per chunk)
└── *_embeddings.npy  # numpy array of embeddings matching JSONL line order
```

The script:
1. Scans JSONL files to discover attribute keys
2. Creates Weaviate collections with appropriate data types
3. Inserts documents, then chunks with vector embeddings
4. Establishes `document` references from chunks to their parent documents
