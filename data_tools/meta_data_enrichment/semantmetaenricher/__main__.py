import argparse
import dataclasses
import json
import sys
from classconfig import Config
from .db import Refused
from .pipeline import EnrichmentPipeline


def endpoint_confirmed(host: str, port: int, confirmed: str | None) -> bool:
    """Whether ``--confirm-endpoint`` names the configured Weaviate endpoint ``HOST:PORT``.

    A run and ``--create-test-collection`` write, and the production store is reached as
    ``localhost`` on its server, so the endpoint is confirmed for every write, not only for
    remote hosts. Prints the refusal or the endpoint to stderr.
    """
    endpoint = f"{host}:{port}"
    if confirmed != endpoint:
        print(f"Refusing to run: configured Weaviate endpoint {endpoint}, --confirm-endpoint {confirmed}",
              file=sys.stderr)
        return False
    print(f"Weaviate endpoint: {endpoint}", file=sys.stderr)
    return True


def report(result) -> int:
    """Print the summary as JSON (stdout) and any refusal (stderr); return the exit code."""
    print(json.dumps(dataclasses.asdict(result), indent=2))
    if result.refused:
        print(f"Refused, nothing written: {result.refused}", file=sys.stderr)
    return result.exit_code()


def _prompt(question: str, default: str = None, allow_empty: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"{question}{suffix}: ").strip()
        if answer:
            return answer
        if default is not None:
            return default
        if allow_empty:
            return ""
        print("This value is required.")


def _prompt_int(question: str, default: int) -> int:
    while True:
        raw = _prompt(question, default=str(default))
        try:
            return int(raw)
        except ValueError:
            print("Please enter a valid integer.")


def _prompt_yes_no(question: str, default: bool = True) -> bool:
    default_str = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{question} [{default_str}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def _prompt_choice(question: str, choices: list, default: str) -> str:
    choices_str = "/".join(choices)
    while True:
        raw = _prompt(f"{question} ({choices_str})", default=default)
        if raw in choices:
            return raw
        print(f"Please choose one of: {choices_str}")


def run_init_wizard(output_path: str) -> None:
    """Interactively build a configuration file step by step, guiding the user through the most common settings."""
    from .models import TASK_CLASSES

    print("This wizard will help you build a configuration file step by step.")
    print("Press Enter to accept the default shown in [brackets].\n")

    overrides = {}

    print("--- Weaviate connection ---")
    overrides["weaviate_host"] = _prompt("Weaviate host", default="localhost")
    overrides["weaviate_port"] = _prompt_int("Weaviate HTTP/REST port", default=8080)
    overrides["weaviate_grpc_port"] = _prompt_int("Weaviate gRPC port", default=50051)
    weaviate_api_key = _prompt("Weaviate API key (leave empty if not required)", default="", allow_empty=True)
    if weaviate_api_key:
        overrides["weaviate_api_key"] = weaviate_api_key
    overrides["collection"] = _prompt("Weaviate collection name to enrich", default="Chunks")
    overrides["provenance"] = _prompt("Model/version identifier written to classification_provenance "
                                      "(change it whenever the model changes)")

    print("\n--- Classification model ---")
    backend = _prompt_choice("Model backend to use", ["local", "api"], default="local")
    if backend == "local":
        model_path = _prompt("Path to converted local model directory", default="converted_model/")
        device = _prompt("Device to load the model on", default="cuda")
        overrides["model"] = {
            "cls": "LocalHFClassifierModel",
            "config": {"model_path": model_path, "device": device},
        }
    else:
        base_url = _prompt("Base URL for the OpenAI-compatible API", default="https://api.openai.com/v1")
        model_name = _prompt("Model name to use", default="gpt-4o-mini")
        api_key = _prompt("API key (leave empty to use the OPENAI_API_KEY environment variable)", default="", allow_empty=True)
        model_config = {"base_url": base_url, "model_name": model_name}
        if api_key:
            model_config["api_key"] = api_key
        overrides["model"] = {"cls": "APIModel", "config": model_config}

    print(f"\n--- Classification tasks ({len(TASK_CLASSES)} available) ---")
    if _prompt_yes_no("Enable all available tasks?", default=True):
        overrides["field_tasks"] = {task: task for task in TASK_CLASSES}
    else:
        print("Available tasks: " + ", ".join(TASK_CLASSES))
        chosen = _prompt("Comma-separated list of task names to enable", default=",".join(TASK_CLASSES))
        chosen_tasks = [t.strip() for t in chosen.split(",") if t.strip()]
        invalid = [t for t in chosen_tasks if t not in TASK_CLASSES]
        if invalid:
            raise ValueError(f"Unknown task(s): {', '.join(invalid)}")
        overrides["field_tasks"] = {task: task for task in chosen_tasks}

    Config(EnrichmentPipeline, file_override_user_defaults=overrides).save(output_path)
    print(f"\nConfiguration written to '{output_path}'.")
    print("It is pre-filled with your answers; everything else was left at its commented default - review it before running the pipeline.")


def main():
    parser = argparse.ArgumentParser(
        description="Classify the UNPROCESSED chunks of a Weaviate collection: fill only their missing "
                    "classification fields and set classification_provenance. Exit code 0 when nothing selected "
                    "is left UNPROCESSED, 1 when chunks remain, 2 when refused."
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
        "--init-wizard",
        metavar="OUTPUT_PATH",
        help="Interactively build a YAML configuration file step by step, guiding you through the most common settings."
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
        help="Create MetaDataEnrichmentTest collection inside Weaviate with 10 Czech historical records, "
             "the mapped fields and classification_provenance, every record UNPROCESSED. An existing "
             "MetaDataEnrichmentTest collection is refused unless --force is given."
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
        help="Read-only: check the configuration and the schema and count the UNPROCESSED chunks a run would "
             "select. Loads no model, writes nothing. Exit code 0 when none is left, 1 when chunks are, "
             "2 when a run would be refused."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="With --create-test-collection: delete an existing MetaDataEnrichmentTest collection and create it again."
    )
    
    args = parser.parse_args()
    if args.check and (args.create_test_collection or args.init or args.init_wizard or args.convert_ckpt):
        parser.error("--check takes neither --create-test-collection, --init, --init-wizard nor --convert-ckpt")
    
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
                fields = list(pipeline.field_tasks)
            else:
                print("No config file provided. Using default connection settings (localhost:8080)...")
                from .models import TASK_CLASSES
                host = "localhost"
                port = 8080
                grpc_port = 50051
                api_key = None
                headers = None
                fields = list(TASK_CLASSES)

            if not endpoint_confirmed(host, port, args.confirm_endpoint):
                sys.exit(2)

            client = get_client(
                host=host,
                port=port,
                grpc_port=grpc_port,
                api_key=api_key,
                headers=headers
            )
            try:
                create_test_collection(client, fields, replace=args.force)
            finally:
                client.close()
                print("Weaviate connection closed.")
            sys.exit(0)
        except Refused as e:
            print(f"Refused: {e}", file=sys.stderr)
            sys.exit(2)
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

    if args.init_wizard:
        try:
            run_init_wizard(args.init_wizard)
            sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            print("\nAborted.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error generating configuration: {e}", file=sys.stderr)
            sys.exit(1)

    if not args.config:
        parser.print_help()
        sys.exit(1)
        
    try:
        print(f"Loading configuration from '{args.config}'...")
        pipeline = EnrichmentPipeline.create(args.config)
    except Exception as e:
        print(f"Invalid configuration: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(2)

    if args.check:
        try:
            sys.exit(report(pipeline.check()))
        except Exception as e:
            print(f"Check failed: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(2)

    if not endpoint_confirmed(pipeline.weaviate_host, pipeline.weaviate_port, args.confirm_endpoint):
        sys.exit(2)

    try:
        sys.exit(report(pipeline.run()))
    except KeyboardInterrupt:
        print("\nInterrupted. Classified chunks are kept; the rest stay UNPROCESSED for the next run.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"Pipeline execution failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
