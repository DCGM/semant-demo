## Summary how are/should be chunks and documents stored in Weaviate DB

Weaviate schema: [create_schema.py](https://github.com/michal-hradis/db_benchmarks/blob/2b07c5eaed169e91a4565fa21976bbb18648c542/weaviate_benchmark/create_schema.py#L4)
Updated weaviate schema: [create_schema.py](https://github.com/Martin-Toma/db_benchmarks/blob/collection-and-tag-update/weaviate_benchmark/create_schema.py). The differences are:
- tag collection (added, does not exist in original)
- references from TextChunk to 
    - userCollection
    - automaticTag
    - positiveTag
    - negativeTag

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
and weavaite metadata
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
