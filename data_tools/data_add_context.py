import json
import argparse
import glob
from tqdm import tqdm



def parse_args():
    parser = argparse.ArgumentParser(
        description="Process a JSONL file. Read all records, open a .jsonl file of that document in reference directory, " \
        "get preceding and following records and add them to the records as context ('prefix' and 'suffix'). " \
        "Write the updated records to a new JSONL file."
    )
    parser.add_argument(
        "-i", "--input-file", type=str, required=True,
        help="Path to the source JSONL file to process."
    )
    parser.add_argument(
        "-o", "--output-file", type=str, required=True,
        help="Path to the output JSONL file to write processed records to."
    )
    parser.add_argument(
        "--reference-dir", type=str, required=True,
        help="Directory containing reference JSONL files for context. Each file should be named <document_id>.jsonl and contain records for that document with 'order' field."
    )

    return parser.parse_args()


def get_context(record: dict, reference_dir: str) -> (str, str):
    """Get prefix and suffix context for a given record based on its document_id and order."""
    order = record.get("order")
    document_id = record.get("document")
    try:
        with open(f"{reference_dir}/{document_id}.jsonl", "r", encoding="utf-8") as ref_file:
            ref_records = [json.loads(line) for line in ref_file]
        
        prefix_order = order - 1
        suffix_order = order + 1

        if ref_records[order].get("id") != record.get("id"):
            raise ValueError(f"Record with order {order} in document {document_id} does not match the input record.")
    
        prefix_record = ref_records[prefix_order] if prefix_order >= 0 else None
        suffix_record = ref_records[suffix_order] if suffix_order < len(ref_records) else None

        return prefix_record, suffix_record
    except FileNotFoundError:
        print(f"Reference file for document {document_id} not found in {reference_dir}. No context will be added.")
        return None, None


def main():
    args = parse_args()

    with open(args.input_file, 'r', encoding='utf-8') as infile, \
        open(args.output_file, 'w', encoding='utf-8') as outfile:
            for line in tqdm(infile, desc="Processing records", smoothing=0.05):
                record = json.loads(line)
                prefix, suffix = get_context(record, args.reference_dir)

                if prefix:
                    record["prefix"] = prefix.get("text", "")

                if suffix:
                    record["suffix"] = suffix.get("text", "")

                outfile.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    main()
