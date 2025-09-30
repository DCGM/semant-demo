"""
Print the number of objects/documents in each Weaviate collection.

Supports:
  - Local Weaviate (default)
  - Weaviate Cloud (WCS) via --cluster-url and --api-key
  - Custom host/ports via --http-host/--http-port/--grpc-port

Requires: weaviate-client >= 4
    pip install "weaviate-client>=4,<5"
"""


import argparse

from db_tools.db_common import connect_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the number of documents in each Weaviate collection."
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--local",
        action="store_true",
        help="Connect to a local Weaviate (default if no other mode is chosen).",
    )
    mode.add_argument(
        "--cluster-url",
        help="WCS cluster URL, e.g. https://your-cluster.weaviate.network",
    )

    parser.add_argument(
        "--api-key",
        help="API key for WCS (used only when --cluster-url is provided).",
    )

    # Custom connection (defaults are localhost:8080/50051)
    parser.add_argument("--http-host", default="127.0.0.1", help="HTTP host (default: 127.0.0.1)")
    parser.add_argument("--http-port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument("--http-secure", action="store_true", help="Use HTTPS for HTTP API")

    parser.add_argument("--grpc-host", help="gRPC host (default: same as http-host)")
    parser.add_argument("--grpc-port", type=int, default=50051, help="gRPC port (default: 50051)")
    parser.add_argument("--grpc-secure", action="store_true", help="Use TLS for gRPC")

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output counts as JSON instead of pretty text.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    with connect_client(args) as client:
        collections = client.collections.list_all()

        if not collections:
            if args.json:
                import json
                print(json.dumps({}, indent=2))
            else:
                print("No collections found.")
            return 0

        counts = {}
        for name in collections:
            coll = client.collections.get(name)  # live Collection

            # ---- count objects
            agg = coll.aggregate.over_all(total_count=True)
            counts[name] = int(agg.total_count or 0)

            # ---- print schema (properties + types), robust across client versions
            cfg = coll.config.get()  # config object (version-dependent fields)

            # try attribute form first
            props_list = []
            try:
                # Newer clients expose a typed list at cfg.properties
                for p in cfg.properties:  # may raise AttributeError on some versions
                    dt = getattr(p, "data_type", None) or getattr(p, "dataType", None)
                    if isinstance(dt, list):
                        dt = ", ".join(dt)
                    props_list.append((p.name, dt))
            except AttributeError:
                # Fallback: use dict representation (works on all versions)
                cfg_dict = cfg.to_dict()
                for p in cfg_dict.get("properties", []):
                    name_p = p.get("name")
                    dt = p.get("dataType")
                    if isinstance(dt, list):
                        dt = ", ".join(dt)
                    props_list.append((name_p, dt))

            # Output
            print(f"\nCollection: {name}")
            print(f"  Count: {counts[name]}")
            print("  Properties:")
            if props_list:
                for prop_name, dtype in props_list:
                    print(f"    - {prop_name}: {dtype}")
            else:
                print("    (no properties)")

        if args.json:
            import json
            print(json.dumps(counts, indent=2))
        else:
            longest = max(len(name) for name in counts)
            print("Collection counts:\n")
            for name in sorted(counts):
                print(f"{name.ljust(longest)}  {counts[name]}")

    return 0




if __name__ == "__main__":
    raise SystemExit(main())
