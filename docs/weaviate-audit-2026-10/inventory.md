# Weaviate inventory

- Created: 2026-10-16T10:08:31+00:00
- Target: `localhost:8080` (Weaviate 1.34.4), chunks collection `Chunks` → `Chunks_test`
- Tool: db_benchmark v1, git `985a269`

## Collections

| collection | objects | vector | index | dims | quantizer | compressed (shard) | maxConn | efC | ef | BlockMax WAND | searchable props | refs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| MetaDataEnrichmentTest | 10 | default | hnsw | n/a | none | False | 32 | 128 | -1 | True | 6 | 0 |
| Documents_test | 59008 | default | hnsw | n/a | none | False | 32 | 128 | -1 | False | 20 | 1 |
| Span_test | 12776 | default | hnsw | n/a | none | False | 32 | 128 | -1 | True | 2 | 2 |
| TmpChunks | 32 | (unnamed) | hnsw | 3584 | none | False | 32 | 128 | -1 | True | 2 | 0 |
| Tag_test | 11336 | default | hnsw | n/a | none | False | 32 | 128 | -1 | True | 7 | 1 |
| Chunks_test | 8280272 | default | hnsw | 3584 | rq(8b) | True | 32 | 128 | -1 | False | 21 | 5 |
| Usercollection_test | 122 | default | hnsw | n/a | none | False | 32 | 128 | -1 | True | 5 | 0 |

Aliases: `Chunks` → `Chunks_test`, `Documents` → `Documents_test`, `Span` → `Span_test`, `Tag` → `Tag_test`, `UserCollection` → `Usercollection_test`

## Vector index coverage (self-retrieval)

300 randomly sampled objects of `Chunks` (vector `default`, seed 374): own object in top-10 for **2/300** (0.0067); found by a query restricted to its own id: **3/300** (0.01). A healthy index finds nearly all of them.

## Disk

- Data filesystem: 2702.1 GiB used of 3665.8 GiB, 963.8 GiB free
- Backup filesystem: 1293.4 GiB free of 43173.3 GiB
- Files listed via `file list files.txt` (data directory not fully readable by this user)
- Total data directory: 317.6 GiB

| directory | size |
|---|---|
| chunks_test | 316.1 GiB |
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
| lsm/objects | 252.4 GiB |
| lsm/property_text_searchable | 24.9 GiB |
| lsm/property_text | 19.1 GiB |
| lsm/property_start_page_id | 2.9 GiB |
| lsm/property_title | 1.4 GiB |
| lsm/property_start_page_id_searchable | 1.3 GiB |
| lsm/vectors_compressed_default | 1.1 GiB |
| lsm/property_subject_domain_searchable | 1.1 GiB |
| lsm/property__id | 1.1 GiB |
| vectors_default.hnsw.commitlog.d | 1.0 GiB |
| lsm/property_reliability_signals_searchable | 0.8 GiB |
| lsm/property_structural_form_searchable | 0.8 GiB |
| lsm/property_title_searchable | 0.7 GiB |
| lsm/property_emotional_tone_searchable | 0.7 GiB |
| lsm/property_temporal_reference_frame_searchable | 0.7 GiB |

`vectors_compressed_default` segments (largest first): 0.7 GiB, 0.3 GiB, 0.1 GiB, 0.0 GiB, 0.0 GiB, 0.0 GiB, 0.0 GiB

`objects` segments (largest first): 127.3 GiB, 57.5 GiB, 46.6 GiB, 14.5 GiB, 6.5 GiB, 0.0 GiB, 0.0 GiB

## Memory

- Host: 187.9 GiB total, 14.5 GiB available, page cache 14.8 GiB, swap 0.0 GiB, ZFS ARC 0.0 GiB (max 0.0 GiB)
- Container cgroup: current 17.3 GiB (anon 3.6 GiB, file cache 13.0 GiB), peak since start 95.0 GiB, limit 98.0 GiB, OOM kills 0

## Log signals

10503 lines from 2026-09-21T22:21:32Z to 2026-10-16T10:08:23Z; startups 4, lines mentioning panic 0.

| count | level | action | message |
|---|---|
| 758 | `warning | - | Number of found nested reference results exceeds configured QUERY_MAXIMUM_RESULTS. This ma` |
| 53 | `warning | read_disk_use | disk usage currently at N%, threshold set to N%` |
| 24 | `error | backup_status | coordinator cannot get status: metadata not found: "": get object path could not find /var` |
| 4 | `warning | graphql_rebuild | ignoring ref prop "document" on class "Chunks_test", because it contains reference to none` |
| 3 | `warning | graphql_rebuild | ignoring ref prop "userCollection" on class "Chunks_test", because it contains reference t` |
| 2 | `warning | graphql_rebuild | ignoring ref prop "automaticTag" on class "Chunks_test", because it contains reference to ` |
| 2 | `warning | graphql_rebuild | ignoring ref prop "negativeTag" on class "Chunks_test", because it contains reference to n` |
| 2 | `warning | graphql_rebuild | ignoring ref prop "positiveTag" on class "Chunks_test", because it contains reference to n` |
| 1 | `warning | - | log level not recognized, defaulting to info` |
| 1 | `warning | - | Multiple vector spaces are present, GraphQL Explore and REST API list objects endpoint mod` |
| 1 | `warning | raft | heartbeat timeout reached, starting election` |
| 1 | `warning | graphql_rebuild | ignoring ref prop "tag" on class "Span_test", because it contains reference to nonexistent` |
| 1 | `warning | graphql_rebuild | ignoring ref prop "userCollection" on class "Tag_test", because it contains reference to n` |
| 1 | `error | try_backup | invalid backup id: 'BACKUP_N' allowed characters are lowercase, N-N, _, -` |

## Backups (backup-filesystem module)

| id | status | size | started |
|---|---|---|---|
| pre-document-cleanup-281-prod | SUCCESS | 193.2 GiB | 2026-10-12T13:39:14 |
| full_2026-09-21_utc_1790030115s | SUCCESS | 267.8 GiB | 2026-09-21T22:35:15 |
| full_2026-09-17_utc_1789680203s | SUCCESS | 268.3 GiB | 2026-09-17T21:23:23 |
| full_2026-08-31_utc_1788157021s_origin | SUCCESS | 255.2 GiB | 2026-08-31T06:17:21 |
| full_2026-08-28_utc_1787910198s | SUCCESS | 188.4 GiB | 2026-08-28T09:43:19 |
| full_2026-08-25_utc_1787664116s | SUCCESS | 255.2 GiB | 2026-08-25T13:21:56 |
| full_2026-08-18_utc_1787019366s | SUCCESS | 255.3 GiB | 2026-08-18T02:16:06 |
| full-migration_2026-08-11_utc_1786463154 | SUCCESS | 255.3 GiB | 2026-08-11T15:46:04 |
