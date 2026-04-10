#!/usr/bin/env python3
# Adding generated titles to text chunks in jsonl format

import json
import argparse
from pathlib import Path

from tqdm import tqdm


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("titles_file", type=str,
                        help="JSONL file with generated titles, each line should be a JSON object with 'custom_id' and 'content' fields")
    parser.add_argument("input_chunks_directory", type=str)
    parser.add_argument("output_chunks_directory", type=str)
    parser.add_argument("--allow_missing_titles", action="store_true",
                        help="If set, allows text chunks without generated titles, else exception will be thrown.")
    return parser.parse_args()


def load_titles(titles_file: str) -> dict[str, dict[str, str]]:
    """
    Loads titles from a JSONL file.

    :param titles_file: JSONL file with titles
    :return: dict
        doc_id:
            chunk_id: title
    """
    titles = {}
    with open(titles_file) as titles_file:
        for line in titles_file:
            record = json.loads(line)
            doc_id, chunk_id = record["custom_id"].split("/")
            title = record["content"]

            if doc_id not in titles:
                titles[doc_id] = {}

            titles[doc_id][chunk_id] = title

    return titles


def get_document_file_paths(chunks_directory: str) -> dict[str, str]:
    """
    Gets a mapping from document ID to the file path of the corresponding text chunks.

    :param chunks_directory: directory with text chunk files, each file should be named {doc_id}.jsonl and contain text chunks for the document with id doc_id
    :return:
     doc_id: file_path
    """

    document_file_paths = {}

    for jsonl_file in Path(chunks_directory).glob("**/*.jsonl"):
        doc_id = jsonl_file.stem
        document_file_paths[doc_id] = jsonl_file

    return document_file_paths


def main():
    args = parse_args()
    output_chunks_directory = Path(args.output_chunks_directory)
    if output_chunks_directory.is_dir() and any(output_chunks_directory.iterdir()):
        raise RuntimeError(f"Output directory {args.output_chunks_directory} already exists, please specify non-existing directory or empty directory.")

    output_chunks_directory.mkdir(parents=True, exist_ok=True)

    titles = load_titles(args.titles_file)
    document_file_paths = get_document_file_paths(args.input_chunks_directory)

    if not args.allow_missing_titles and (len(titles) != len(document_file_paths) or set(titles.keys()) != set(document_file_paths.keys())):
        raise RuntimeError(
            "Number of documents with generated titles does not match the number of documents with text chunks. If you want to allow missing titles, use --allow_missing_titles flag."
        )

    for doc_id, file_path in tqdm(document_file_paths.items(), total=len(document_file_paths), desc="Adding titles to text chunks"):
        if doc_id not in titles:
            if args.allow_missing_titles:
                continue
            raise RuntimeError(
                f"Missing generated titles for document {doc_id}. If you want to allow missing titles, use --allow_missing_titles flag."
            )
        with open(file_path) as f, open(output_chunks_directory / f"{doc_id}.jsonl", "w") as output_file:
            for line in f:
                record = json.loads(line)
                if record["id"] not in titles[doc_id]:
                    if args.allow_missing_titles:
                        continue
                    raise RuntimeError(
                        f"Missing title for chunk {record['id']} of document {doc_id}. If you want to allow missing titles, use --allow_missing_titles flag."
                    )
                record["title"] = titles[doc_id][record["id"]]

                print(
                    json.dumps(record, ensure_ascii=False),
                    file=output_file
                )


if __name__ == "__main__":
    main()
