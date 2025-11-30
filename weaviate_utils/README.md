## Setup weaviate
```
cd weaviate_utils

docker-compose up -d

conda activate semant

python create_schema.py

python db_insert_jsonl.py --source-dir C:\Users\marti\Music\semANT_public\semant-demo\weaviate_utils\server_setup\ --delete-old

python update_metadata.py --logging-on 
------
python insert_jsonl.py --source-dir C:\Users\marti\Music\semANT_public\semant-demo\weaviate_utils\server_setup\ --delete-old

python insert_jsonl.py --source-dir /mnt/ssd2/weaviate_data/all.768/chunks.vec.lang/ --delete-old
```

connect:
```
ssh -L 8080:localhost:8080 xtomas36@semant.cz
```

## Summary how are/should be chunks and documents stored in Weaviate DB

Weaviate schema: [create_schema.py](https://github.com/michal-hradis/db_benchmarks/blob/2b07c5eaed169e91a4565fa21976bbb18648c542/weaviate_benchmark/create_schema.py#L4)
Updated weaviate schema: [create_schema.py](https://github.com/Martin-Toma/db_benchmarks/blob/collection-and-tag-update/weaviate_benchmark/create_schema.py). The differences are:
- tag collection (added, does not exist in original)
- references from TextChunk to 
    - userCollection
    - automaticTag
    - positiveTag
    - negativeTag
- Also on the semant server the class is named 'Chunks' not 'TextChunks' as in the schema script

The db has this header:
```
id | library | parent_id | parent_library | public | order | record_type | page_type  | date | number | start_date  | end_date |image_path | mods_path | page_xml_path | metadata_json | title | page_placement | created_date | updated_date
```
Comparison of metadata_json:
```
    TITLE = "Title"
    SUBTITLE = "Subtitle"
    PART_NAME = "PartName"
    PART_NUMBER = "PartNumber"
    SERIES_NAME = "SeriesName"
    SERIES_NUMBER = "SeriesNumber"
    EDITION = "Edition"
    PUBLISHER = "Publisher"
    PLACE_TERM = "PlaceTerm"
    DATE_ISSUED = "DateIssued"
    MANUFACTURE_PUBLISHER = "ManufacturePublisher"
    MANUFACTURE_PLACE_TERM = "ManufacturePlaceTerm"
    AUTHOR = "Author"
    ILLUSTRATOR = "Illustrator"
    TRANSLATOR = "Translator"
    EDITOR = "Editor"
    REDAKTOR = "Redaktor"
    LANGUAGE = "Language"

```
and weaviate metadata
```
"title": parsed_filename["title"],
"subtitle": "",
"partNumber": 1,
"partName": "",
"dateIssued": parsed_filename["date"] + "T16:00:00+00:00",
"yearIssued": int(parsed_filename["year"]),
"author": [parsed_filename["last_part"]],
"publisher": "",
"language": ["cs"],
"description": "",
"url": parsed_filename["id"],
"public": True,
"documentType": "textfile",
"keywords": [],
"genre": parsed_filename["rubrik"],
"placeOfPublication": "",
```

In weaviate but missing/renamed in metadata_json: 
- yearIssued - can be extracted from dateIssued
- description

- url - in sql id
- public - in sql there is a column
- documentType - sql columns record_type or page_type
- keywords - missing
- genre - missing
- placeOfPublication - == PLACE_TERM 

In metadata_json missing in weaviate:

-    SERIES_NAME = "SeriesName"
-    SERIES_NUMBER = "SeriesNumber"
-    EDITION = "Edition"
-    MANUFACTURE_PUBLISHER = "ManufacturePublisher"
-    MANUFACTURE_PLACE_TERM = "ManufacturePlaceTerm"
-    ILLUSTRATOR = "Illustrator"
-    TRANSLATOR = "Translator"
-    EDITOR = "Editor"
-    REDAKTOR = "Redaktor"

## Relevant scripts
(This part is a copy of issue with added links)
[create_schema.py](https://github.com/michal-hradis/db_benchmarks/blob/2b07c5eaed169e91a4565fa21976bbb18648c542/weaviate_benchmark/create_schema.py#L4) - old definition of metadata attributes

[db_prepare_documents.py](https://github.com/michal-hradis/db_benchmarks/blob/2b07c5eaed169e91a4565fa21976bbb18648c542/semant/db_prepare_documents.py#L4) - creates text chunks from OCR outputs - shows how to access the metadata database

[insert_documents.py](https://github.com/michal-hradis/db_benchmarks/blob/2b07c5eaed169e91a4565fa21976bbb18648c542/weaviate_benchmark/insert_documents.py#L4) - shows some mapping between metadata and weaviate attributes

## Server weaviate schema

Only these 2 classes:

```
xtomas36@semant:~$ curl http://localhost:8080/v1/schema | jq '.classes[].class'
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100  2538    0  2538    0     0  2892k      0 --:--:-- --:--:-- --:--:-- 2478k
"Chunks"
"Documents"
```

Use command: `curl http://localhost:8080/v1/schema | jq`

```
{
  "classes": [
    {
      "class": "Chunks",
      "invertedIndexConfig": {
        "bm25": {
          "b": 0.75,
          "k1": 1.2
        },
        "cleanupIntervalSeconds": 60,
        "stopwords": {
          "additions": null,
          "preset": "en",
          "removals": null
        }
      },
      "multiTenancyConfig": {
        "enabled": false
      },
      "properties": [
        {
          "dataType": [
            "boolean"
          ],
          "indexFilterable": true,
          "indexSearchable": false,
          "name": "end_paragraph"
        },
        {
          "dataType": [
            "int"
          ],
          "indexFilterable": true,
          "indexSearchable": false,
          "name": "from_page"
        },
        {
          "dataType": [
            "text"
          ],
          "indexFilterable": true,
          "indexSearchable": true,
          "name": "language",
          "tokenization": "word"
        },
        {
          "dataType": [
            "text"
          ],
          "indexFilterable": true,
          "indexSearchable": true,
          "name": "start_page_id",
          "tokenization": "word"
        },
        {
          "dataType": [
            "text"
          ],
          "indexFilterable": true,
          "indexSearchable": true,
          "name": "text",
          "tokenization": "word"
        },
        {
          "dataType": [
            "int"
          ],
          "indexFilterable": true,
          "indexSearchable": false,
          "name": "to_page"
        },
        {
          "dataType": [
            "Documents"
          ],
          "indexFilterable": true,
          "indexSearchable": false,
          "name": "document"
        }
      ],
      "replicationConfig": {
        "factor": 1
      },
      "shardingConfig": {
        "virtualPerPhysical": 128,
        "desiredCount": 1,
        "actualCount": 1,
        "desiredVirtualCount": 128,
        "actualVirtualCount": 128,
        "key": "_id",
        "strategy": "hash",
        "function": "murmur3"
      },
      "vectorIndexConfig": {
        "skip": false,
        "cleanupIntervalSeconds": 300,
        "maxConnections": 64,
        "efConstruction": 128,
        "ef": -1,
        "dynamicEfMin": 100,
        "dynamicEfMax": 500,
        "dynamicEfFactor": 8,
        "vectorCacheMaxObjects": 1000000000000,
        "flatSearchCutoff": 40000,
        "distance": "cosine",
        "pq": {
          "enabled": false,
          "bitCompression": false,
          "segments": 0,
          "centroids": 256,
          "trainingLimit": 100000,
          "encoder": {
            "type": "kmeans",
            "distribution": "log-normal"
          }
        },
        "bq": {
          "enabled": false
        }
      },
      "vectorIndexType": "hnsw",
      "vectorizer": "none"
    },
    {
      "class": "Documents",
      "invertedIndexConfig": {
        "bm25": {
          "b": 0.75,
          "k1": 1.2
        },
        "cleanupIntervalSeconds": 60,
        "stopwords": {
          "additions": null,
          "preset": "en",
          "removals": null
        }
      },
      "multiTenancyConfig": {
        "enabled": false
      },
      "properties": [],
      "replicationConfig": {
        "factor": 1
      },
      "shardingConfig": {
        "virtualPerPhysical": 128,
        "desiredCount": 1,
        "actualCount": 1,
        "desiredVirtualCount": 128,
        "actualVirtualCount": 128,
        "key": "_id",
        "strategy": "hash",
        "function": "murmur3"
      },
      "vectorConfig": {
        "default": {
          "vectorIndexConfig": {
            "skip": false,
            "cleanupIntervalSeconds": 300,
            "maxConnections": 64,
            "efConstruction": 128,
            "ef": -1,
            "dynamicEfMin": 100,
            "dynamicEfMax": 500,
            "dynamicEfFactor": 8,
            "vectorCacheMaxObjects": 1000000000000,
            "flatSearchCutoff": 40000,
            "distance": "cosine",
            "pq": {
              "enabled": false,
              "bitCompression": false,
              "segments": 0,
              "centroids": 256,
              "trainingLimit": 100000,
              "encoder": {
                "type": "kmeans",
                "distribution": "log-normal"
              }
            },
            "bq": {
              "enabled": false
            }
          },
          "vectorIndexType": "hnsw",
          "vectorizer": {
            "none": {}
          }
        }
      }
    }
  ]
}
```