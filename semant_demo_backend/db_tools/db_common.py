import argparse

import weaviate


def connect_client(args: argparse.Namespace) -> weaviate.WeaviateClient:
    if args.cluster_url:
        headers = {"Authorization": f"Bearer {args.api_key}"} if args.api_key else None
        return weaviate.connect_to_wcs(cluster_url=args.cluster_url, headers=headers)

    if args.local:
        return weaviate.connect_to_local()

    return weaviate.connect_to_custom(
        http_host=args.http_host,
        http_port=args.http_port,
        http_secure=args.http_secure,
        grpc_host=args.grpc_host or args.http_host,
        grpc_port=args.grpc_port,
        grpc_secure=args.grpc_secure,
    )
