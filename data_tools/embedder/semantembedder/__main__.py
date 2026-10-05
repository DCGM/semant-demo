import argparse
import asyncio
import sys
from classconfig import Config
from .pipeline import EmbeddingPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Embed Weaviate records via an OpenAI-compatible (vLLM) API and store them as a named vector."
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
        "--create-test-collection",
        action="store_true",
        help="Create EmbedderTest collection (with named vectors) inside Weaviate with 10 Czech historical records."
    )

    args = parser.parse_args()

    if args.create_test_collection:
        try:
            from .db import get_async_client, create_test_collection
            if args.config:
                print(f"Loading Weaviate connection settings from config '{args.config}'...")
                pipeline = EmbeddingPipeline.create(args.config)
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

            async def create():
                async with get_async_client(
                    host=host,
                    port=port,
                    grpc_port=grpc_port,
                    api_key=api_key,
                    headers=headers
                ) as client:
                    await create_test_collection(client)
                print("Weaviate connection closed.")

            asyncio.run(create())
            sys.exit(0)
        except Exception as e:
            print(f"Error creating test collection: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)

    if args.init:
        try:
            print(f"Generating template configuration file at '{args.init}'...")
            cfg = Config(EmbeddingPipeline)
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
        pipeline = EmbeddingPipeline.create(args.config)
        pipeline.run()
    except KeyboardInterrupt:
        print("\nInterrupted. Already written vectors are kept; run the pipeline again to continue.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Pipeline execution failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
