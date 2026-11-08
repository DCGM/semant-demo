import argparse
import asyncio
import sys
from classconfig import Config
from .pipeline import EmbeddingPipeline


def endpoint_confirmed(host: str, port: int, confirmed: str | None) -> bool:
    """Whether ``--confirm-endpoint`` names the configured Weaviate endpoint ``HOST:PORT``.

    Every run writes (vectors, the schema or the test collection), and the production store is
    reached as ``localhost`` on its server, so the endpoint is confirmed for every run, not only
    for remote hosts. Prints the refusal or the endpoint to stderr.
    """
    endpoint = f"{host}:{port}"
    if confirmed != endpoint:
        print(f"Refusing to run: configured Weaviate endpoint {endpoint}, --confirm-endpoint {confirmed}",
              file=sys.stderr)
        return False
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    return True


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
        help="Create EmbedderTest collection (with named vectors) inside Weaviate with 10 Czech historical records. "
             "An existing EmbedderTest collection is refused unless --force is given."
    )
    parser.add_argument(
        "--confirm-endpoint",
        metavar="HOST:PORT",
        help="Required for a pipeline run and --create-test-collection: the Weaviate endpoint of the config "
             "(weaviate_host:weaviate_port; localhost:8080 for --create-test-collection without a config). "
             "A missing or different value is refused (exit code 2) before connecting. "
             "--check needs none and ignores it."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Read-only: count the records a run would embed (with the vector, without it, empty input). "
             "No schema change, no embedding requests, no writes. It reads every record with the vector, "
             "like a run. Exit code 0 when nothing is left to embed, 1 when records are, 2 when the check fails "
             "or a run would be refused."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --create-test-collection: delete an existing EmbedderTest collection and create it again."
    )

    args = parser.parse_args()
    if args.check and (args.create_test_collection or args.init):
        parser.error("--check takes neither --create-test-collection nor --init")

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

            if not endpoint_confirmed(host, port, args.confirm_endpoint):
                sys.exit(2)

            async def create():
                async with get_async_client(
                    host=host,
                    port=port,
                    grpc_port=grpc_port,
                    api_key=api_key,
                    headers=headers
                ) as client:
                    await create_test_collection(client, replace=args.force)
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

    if args.check:
        try:
            print(f"Loading configuration from '{args.config}'...")
            stats = EmbeddingPipeline.create(args.config).check()
        except Exception as e:
            print(f"Check failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(2)
        if stats.refused:
            print(f"A run would be refused: {stats.refused}", file=sys.stderr)
            sys.exit(2)
        sys.exit(1 if stats.missing else 0)

    try:
        print(f"Loading configuration from '{args.config}'...")
        pipeline = EmbeddingPipeline.create(args.config)
    except Exception as e:
        print(f"Invalid configuration: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    if not endpoint_confirmed(pipeline.weaviate_host, pipeline.weaviate_port, args.confirm_endpoint):
        sys.exit(2)

    try:
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
