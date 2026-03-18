import json
import argparse
from semant_demo.main import app

def export_schema(output_file: str):
    with open(output_file, "w") as f:
        json.dump(app.openapi(), f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export OpenAPI schema")
    parser.add_argument(
        "-o",
        "--output",
        default="openapi.json",
        help="Output file path (default: openapi.json)"
    )

    args = parser.parse_args()
    export_schema(args.output)