import argparse
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
import json

def parse_args():
    parser = argparse.ArgumentParser(description="Print all chunks from Weaviate database.")
    parser.add_argument(
        "--chunk-collection",
        type=str,
        default="Chunks",
        help="Name of the chunk collection."
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["pretty", "json"],
        default="pretty",
        help="Output format: 'pretty' for readable format or 'json' for JSON output."
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Optional: Save output to a file instead of printing to console."
    )
    return parser.parse_args()


def print_chunk_pretty(chunk, index):
    """Print a chunk in a human-readable format."""
    print(f"\n{'='*80}")
    print(f"CHUNK #{index + 1}")
    print(f"{'='*80}")
    print(f"UUID: {chunk.uuid}")
    print(f"\nProperties:")
    print("-" * 80)

    for key, value in sorted(chunk.properties.items()):
        if isinstance(value, list):
            print(f"  {key:20s}: {', '.join(str(v) for v in value)}")
        elif value is not None:
            print(f"  {key:20s}: {value}")


def main():
    args = parse_args()

    # Connect to Weaviate
    client = WeaviateClient(
        connection_params=ConnectionParams.from_params(
            http_host="localhost", http_port=8080, http_secure=False,
            grpc_host="localhost", grpc_port=50051, grpc_secure=False,
        )
    )

    try:
        client.connect()

        if not client.is_ready():
            print("ERROR: Weaviate is not ready.")
            return

        # Get the chunk collection
        chunk_collection = client.collections.get(args.chunk_collection)

        # Fetch all chunks
        print(f"Fetching chunks from collection: {args.chunk_collection}")
        response = chunk_collection.query.fetch_objects(limit=1000)

        chunks = response.objects

        if not chunks:
            print(f"\nNo chunks found in collection '{args.chunk_collection}'")
            return

        print(f"\nFound {len(chunks)} chunk(s)\n")

        output_lines = []

        if args.format == "pretty":
            for idx, chunk in enumerate(chunks):
                if args.output_file:
                    output_lines.append("=" * 80)
                    output_lines.append(f"CHUNK #{idx + 1}")
                    output_lines.append("=" * 80)
                    output_lines.append(f"UUID: {chunk.uuid}")
                    output_lines.append("\nProperties:")
                    output_lines.append("-" * 80)
                    for key, value in sorted(chunk.properties.items()):
                        if isinstance(value, list):
                            output_lines.append(
                                f"  {key:20s}: {', '.join(str(v) for v in value)}"
                            )
                        elif value is not None:
                            output_lines.append(f"  {key:20s}: {value}")
                    output_lines.append("")
                else:
                    print_chunk_pretty(chunk, idx)

        else:  # JSON format
            chunks_json = []
            for chunk in chunks:
                chunks_json.append({
                    "uuid": str(chunk.uuid),
                    "properties": chunk.properties
                })

            json_output = json.dumps(chunks_json, indent=2, ensure_ascii=False)

            if args.output_file:
                output_lines.append(json_output)
            else:
                print(json_output)

        # Write to file if needed
        if args.output_file:
            with open(args.output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(output_lines))
            print(f"\nOutput saved to: {args.output_file}")

        print(f"\n{'='*80}")
        print(f"Total chunks: {len(chunks)}")
        print(f"{'='*80}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
