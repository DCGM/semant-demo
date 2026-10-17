# Weaviate inventory

- Created: 2026-10-17T12:21:32+00:00
- Target: `localhost:8080` (Weaviate 1.40.1), chunks collection `Chunks` → `Chunks_test`
- Tool: db_benchmark v2, git `8e22680`

## Collections

| collection | objects | vector | index | dims | quantizer | compressed (shard) | maxConn | efC | ef | BlockMax WAND | searchable props | refs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TmpChunks | 32 | (unnamed) | hnsw | 3584 | none | False | 32 | 128 | -1 | True | 2 | 0 |
| Chunks_test | 8280272 | Qwen3_Embedding_0_6B | hnsw | 1024 | rq(8b) | True | 32 | 128 | -1 | True | 21 | 5 |
| Span_test | 12869 | default | hnsw | none stored | none | False | 32 | 128 | -1 | True | 2 | 2 |
| Usercollection_test | 122 | default | hnsw | none stored | none | False | 32 | 128 | -1 | True | 5 | 0 |
| MetaDataEnrichmentTest | 10 | default | hnsw | none stored | none | False | 32 | 128 | -1 | True | 6 | 0 |
| Documents_test | 59008 | default | hnsw | none stored | none | False | 32 | 128 | -1 | False | 20 | 1 |
| Tag_test | 11336 | default | hnsw | none stored | none | False | 32 | 128 | -1 | True | 7 | 1 |

Aliases: `Chunks` → `Chunks_test`, `Documents` → `Documents_test`, `Span` → `Span_test`, `Tag` → `Tag_test`, `UserCollection` → `Usercollection_test`

## Vector index coverage (self-retrieval)

500 randomly sampled objects of `Chunks` (vector `Qwen3_Embedding_0_6B`, seed 394): own object in top-10 for **500/500** (1); found by a query restricted to its own id: **500/500** (1). A healthy index finds nearly all of them.

## Disk

- Data filesystem: 2652.3 GiB used of 3665.8 GiB, 1013.5 GiB free
- Backup filesystem: 1007.0 GiB free of 43173.3 GiB
- Files listed via `a saved file list` (data directory not fully readable by this user)
- Total data directory: 167.0 GiB

| directory | size |
|---|---|
| chunks_test | 165.4 GiB |
| documents_test | 1.5 GiB |
| tag_test | 0.1 GiB |
| span_test | 0.0 GiB |
| tmpchunks | 0.0 GiB |
| usercollection_test | 0.0 GiB |
| raft | 0.0 GiB |
| metadataenrichmenttest | 0.0 GiB |
| schema.db | 0.0 GiB |
| index.db | 0.0 GiB |
| classifications.db | 0.0 GiB |
| modules.db | 0.0 GiB |

### `documents_test` components

| component | size |
|---|---|
| lsm/objects | 0.5 GiB |
| lsm/property_title_searchable | 0.1 GiB |
| lsm/property__id | 0.1 GiB |
| lsm/property_dateIssued | 0.1 GiB |
| lsm/property_dateIssuedMetadata | 0.1 GiB |
| lsm/property_title | 0.1 GiB |
| lsm/property_subtitle_searchable | 0.1 GiB |
| lsm/property_publisher_searchable | 0.1 GiB |
| lsm/property_titleMetadata_searchable | 0.1 GiB |
| lsm/property_titleMetadata | 0.0 GiB |
| lsm/property_placeOfPublication_searchable | 0.0 GiB |
| lsm/property_subtitle | 0.0 GiB |
| lsm/property_documentType_searchable | 0.0 GiB |
| lsm/property_language_searchable | 0.0 GiB |
| lsm/property_partNumber_searchable | 0.0 GiB |

`objects` segments (largest first): 0.3 GiB, 0.2 GiB, 0.1 GiB, 0.0 GiB

### `chunks_test` components

| component | size |
|---|---|
| lsm/objects | 53.7 GiB |
| lsm/property_text_searchable | 41.7 GiB |
| lsm/property_text | 19.9 GiB |
| lsm/vectors_compressed_Qwen3_Embedding_0_6B | 8.7 GiB |
| lsm/property_start_page_id | 4.6 GiB |
| lsm/property_subject_domain_searchable | 3.0 GiB |
| lsm/property_start_page_id_searchable | 2.8 GiB |
| lsm/property_reliability_signals_searchable | 2.3 GiB |
| lsm/property_structural_form_searchable | 2.3 GiB |
| lsm/property_title | 2.1 GiB |
| lsm/property_emotional_tone_searchable | 2.0 GiB |
| lsm/property_temporal_reference_frame_searchable | 2.0 GiB |
| lsm/property_narrative_perspective_searchable | 2.0 GiB |
| lsm/property__id | 1.9 GiB |
| lsm/property_named_entity_focus_searchable | 1.8 GiB |

`vectors_compressed_Qwen3_Embedding_0_6B` segments (largest first): 5.4 GiB, 2.9 GiB, 0.4 GiB, 0.1 GiB, 0.0 GiB

`objects` segments (largest first): 39.1 GiB, 8.1 GiB, 4.0 GiB, 2.0 GiB, 0.3 GiB, 0.0 GiB, 0.0 GiB

## Memory

- Host: 187.9 GiB total, 85.9 GiB available, page cache 80.1 GiB, swap 0.0 GiB, ZFS ARC 26.0 GiB (max 94.0 GiB)
- Container cgroup: current 79.5 GiB (anon 16.4 GiB, file cache 61.5 GiB), peak since start 98.0 GiB, limit 98.0 GiB, OOM kills 0

## Log signals

486 lines from 2026-10-16T20:45:37Z to 2026-10-17T09:58:10Z; process starts 1, lines mentioning panic 0.

| count | level | action | message (numbers masked) |
|---|---|---|---|
| 7 | warning | lazy_shard_auto_detection | lazy load shard auto-detection result |
| 6 | warning | read_disk_use | disk usage currently at N%, threshold set to N% |
| 4 | warning | graphql_rebuild | ignoring ref prop "document" on class "Chunks_test", because it contains reference to none |
| 3 | warning | graphql_rebuild | ignoring ref prop "userCollection" on class "Chunks_test", because it contains reference t |
| 2 | warning | graphql_rebuild | ignoring ref prop "automaticTag" on class "Chunks_test", because it contains reference to  |
| 2 | warning | graphql_rebuild | ignoring ref prop "negativeTag" on class "Chunks_test", because it contains reference to n |
| 2 | warning | graphql_rebuild | ignoring ref prop "positiveTag" on class "Chunks_test", because it contains reference to n |
| 1 | warning | - | log level not recognized, defaulting to info |
| 1 | warning | - | Multiple vector spaces are present, GraphQL Explore and REST API list objects endpoint mod |
| 1 | warning | raft | heartbeat timeout reached, starting election |
| 1 | warning | graphql_rebuild | ignoring ref prop "tag" on class "Span_test", because it contains reference to nonexistent |
| 1 | warning | graphql_rebuild | ignoring ref prop "userCollection" on class "Tag_test", because it contains reference to n |

## Backups (backup-filesystem module)

| started | status | size | collections |
|---|---|---|---|
| 2026-10-12T13:39:14 | SUCCESS | 193.2 GiB | 7 |
| 2026-09-21T22:35:15 | SUCCESS | 267.8 GiB | 7 |
| 2026-09-17T21:23:23 | SUCCESS | 268.3 GiB | 8 |
| 2026-08-31T06:17:21 | SUCCESS | 255.2 GiB | 7 |
| 2026-08-28T09:43:19 | SUCCESS | 188.4 GiB | 7 |
| 2026-08-25T13:21:56 | SUCCESS | 255.2 GiB | 7 |
| 2026-08-18T02:16:06 | SUCCESS | 255.3 GiB | 7 |
| 2026-08-11T15:46:04 | SUCCESS | 255.3 GiB | 7 |
