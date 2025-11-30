import argparse
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams
import json

def parse_args():
    parser = argparse.ArgumentParser(description="Print all documents from Weaviate database.")
    parser.add_argument("--document-collection", type=str, default="Documents", 
                        help="Name of the document collection.")
    parser.add_argument("--format", type=str, choices=["pretty", "json"], default="pretty",
                        help="Output format: 'pretty' for readable format or 'json' for JSON output.")
    parser.add_argument("--output-file", type=str, default=None,
                        help="Optional: Save output to a file instead of printing to console.")
    return parser.parse_args()


def print_document_pretty(doc, index):
    """Print a document in a human-readable format."""
    print(f"\n{'='*80}")
    print(f"DOCUMENT #{index + 1}")
    print(f"{'='*80}")
    print(f"UUID: {doc.uuid}")
    print(f"\nProperties:")
    print("-" * 80)
    
    for key, value in sorted(doc.properties.items()):
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
        ))
    
    try:
        client.connect()
        
        if not client.is_ready():
            print("ERROR: Weaviate is not ready.")
            return
        
        # Get the document collection
        doc_collection = client.collections.get(args.document_collection)
        
        # Fetch all documents
        print(f"Fetching documents from collection: {args.document_collection}")
        response = doc_collection.query.fetch_objects(limit=1000)
        
        documents = response.objects
        
        if not documents:
            print(f"\nNo documents found in collection '{args.document_collection}'")
            return
        
        print(f"\nFound {len(documents)} document(s)\n")
        
        output_lines = []
        
        if args.format == "pretty":
            for idx, doc in enumerate(documents):
                if args.output_file:
                    output_lines.append("=" * 80)
                    output_lines.append(f"DOCUMENT #{idx + 1}")
                    output_lines.append("=" * 80)
                    output_lines.append(f"UUID: {doc.uuid}")
                    output_lines.append("\nProperties:")
                    output_lines.append("-" * 80)
                    for key, value in sorted(doc.properties.items()):
                        if isinstance(value, list):
                            output_lines.append(f"  {key:20s}: {', '.join(str(v) for v in value)}")
                        elif value is not None:
                            output_lines.append(f"  {key:20s}: {value}")
                    output_lines.append("")
                else:
                    print_document_pretty(doc, idx)
        
        else:  # JSON format
            documents_json = []
            for doc in documents:
                documents_json.append({
                    "uuid": str(doc.uuid),
                    "properties": doc.properties
                })
            
            json_output = json.dumps(documents_json, indent=2, ensure_ascii=False)
            
            if args.output_file:
                output_lines.append(json_output)
            else:
                print(json_output)
        
        # Write to file if specified
        if args.output_file:
            with open(args.output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(output_lines))
            print(f"\nOutput saved to: {args.output_file}")
        
        print(f"\n{'='*80}")
        print(f"Total documents: {len(documents)}")
        print(f"{'='*80}")
    
    finally:
        client.close()


if __name__ == "__main__":
    main()