import argparse
import sys
from classconfig import Config
from .pipeline import EnrichmentPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Run the metadata enrichment pipeline on a Weaviate database."
    )
    parser.add_argument(
        "config",
        nargs="?",
        help="Path to the YAML configuration file to run the pipeline."
    )
    parser.add_argument(
        "--init",
        metavar="OUTPUT_PATH",
        help="Generate a default template YAML configuration file at the specified path."
    )
    parser.add_argument(
        "--convert-ckpt",
        nargs=2,
        metavar=("CKPT_PATH", "OUTPUT_DIR"),
        help="Convert a PyTorch Lightning checkpoint to a standard HuggingFace model directory."
    )
    parser.add_argument(
        "--create-test-collection",
        action="store_true",
        help="Create MetaDataEnrichmentTest collection inside Weaviate with 10 Czech historical records."
    )
    
    args = parser.parse_args()
    
    if args.create_test_collection:
        try:
            from .db import get_client, create_test_collection
            if args.config:
                print(f"Loading Weaviate connection settings from config '{args.config}'...")
                pipeline = EnrichmentPipeline.create(args.config)
                host = pipeline.weaviate_host
                port = pipeline.weaviate_port
                grpc_port = pipeline.weaviate_grpc_port
                api_key = pipeline.weaviate_api_key
                headers = pipeline.weaviate_headers
            else:
                print("No config file provided. Using default connection settings (localhost:8080)...")
                host = "localhost"
                port = 8080
                grpc_port = 50051
                api_key = None
                headers = None
                
            client = get_client(
                host=host,
                port=port,
                grpc_port=grpc_port,
                api_key=api_key,
                headers=headers
            )
            try:
                create_test_collection(client)
            finally:
                client.close()
                print("Weaviate connection closed.")
            sys.exit(0)
        except Exception as e:
            print(f"Error creating test collection: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)
            
    if args.convert_ckpt:
        ckpt_path, output_dir = args.convert_ckpt
        try:
            from .models import convert_lightning_checkpoint
            convert_lightning_checkpoint(ckpt_path, output_dir)
            sys.exit(0)
        except Exception as e:
            print(f"Error converting checkpoint: {e}", file=sys.stderr)
            sys.exit(1)
            
    if args.init:
        try:
            print(f"Generating template configuration file at '{args.init}'...")
            cfg = Config(EnrichmentPipeline)
            cfg.save(args.init)
            print("Template generated successfully. Please edit it to match your environment.")
            sys.exit(0)
        except Exception as e:
            print(f"Error generating template configuration: {e}", file=sys.stderr)
            sys.exit(1)
            
    if not args.config:
        parser.print_help()
        sys.exit(1)
        
    try:
        print(f"Loading configuration from '{args.config}'...")
        pipeline = EnrichmentPipeline.create(args.config)
        pipeline.run()
    except Exception as e:
        print(f"Pipeline execution failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
