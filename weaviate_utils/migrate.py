import argparse
import weaviate
import weaviate.classes.config as wvc
from weaviate.classes.init import AdditionalConfig, Timeout


def parse_args():
    p = argparse.ArgumentParser(description="Migrate collection camelCase -> snake_case and keep original collection name")
    p.add_argument("--source", default="UserCollection", help="Existing collection name")
    p.add_argument("--temp", default=None, help="Temporary collection name used during migration")
    p.add_argument("--keep-temp", action="store_true", help="Keep temporary collection after successful migration")
    p.add_argument("--dry-run", action="store_true", help="Do not write, only print what would happen")
    return p.parse_args()


def connect():
    client = weaviate.connect_to_local(
        port=8080,
        grpc_port=50051,
        additional_config=AdditionalConfig(
            timeout=Timeout(init=30, query=60, insert=120)
        )
    )
    return client


def ensure_source_exists(client, source):
    exists = client.collections.exists(source)
    if not exists:
        raise RuntimeError(f"Source collection not found: {source}")


def create_collection_if_missing(client, collection_name, dry_run=False):
    if client.collections.exists(collection_name):
        print(f"Collection already exists: {collection_name}")
        return

    print(f"Creating collection: {collection_name}")
    if dry_run:
        return

    client.collections.create(
        name=collection_name,
        properties=[
            wvc.Property(name="name", data_type=wvc.DataType.TEXT, description="Name of the collection"),
            wvc.Property(name="user_id", data_type=wvc.DataType.TEXT, description="ID of the user who owns the collection"),
            wvc.Property(name="description", data_type=wvc.DataType.TEXT, description="Description of the collection"),
            wvc.Property(name="color", data_type=wvc.DataType.TEXT, description="Color associated with the collection for UI purposes"),
            wvc.Property(name="created_at", data_type=wvc.DataType.DATE, description="Date of creation of the collection"),
            wvc.Property(name="updated_at", data_type=wvc.DataType.DATE, description="Date of last update of the collection"),
        ],
    )


def map_props(old_props):
    old_props = old_props or {}

    new_props = {
        "name": old_props.get("name"),
        "user_id": old_props.get("user_id"),
        "description": old_props.get("description"),
        "color": old_props.get("color"),
        "created_at": old_props.get("created_at") or old_props.get("createdAt"),
        "updated_at": old_props.get("updated_at") or old_props.get("updatedAt"),
    }

    # remove None values
    return {k: v for k, v in new_props.items() if v is not None}


def copy_objects(client, source, target, dry_run=False):
    src = client.collections.get(source)
    tgt = client.collections.get(target)

    total = 0
    inserted = 0
    skipped = 0

    for obj in src.iterator():
        total += 1
        props = map_props(obj.properties)

        if dry_run:
            inserted += 1
            continue

        try:
            tgt.data.insert(
                uuid=obj.uuid,
                properties=props
            )
            inserted += 1
        except Exception as e:
            # likely duplicate UUID if re-run; skip safely
            skipped += 1
            print(f"Skip uuid={obj.uuid}, reason={e}")

    print(f"Copy done. total={total}, inserted={inserted}, skipped={skipped}")


def count_objects(client, collection_name):
    col = client.collections.get(collection_name)
    cnt = 0
    for _ in col.iterator():
        cnt += 1
    return cnt


def main():
    args = parse_args()
    client = connect()
    temp_name = args.temp or f"{args.source}_tmp_snake"

    try:
        ensure_source_exists(client, args.source)
        if temp_name == args.source:
            raise RuntimeError("Temporary collection name must be different from source.")

        print(f"Source collection: {args.source}")
        print(f"Temporary collection: {temp_name}")

        # Step 1: Copy source -> temporary collection with snake_case mapping
        create_collection_if_missing(client, temp_name, dry_run=args.dry_run)
        copy_objects(client, args.source, temp_name, dry_run=args.dry_run)

        if args.dry_run:
            print("Dry-run finished. No changes were written.")
            return

        # Step 2: Verify temporary copy before touching source
        src_count = count_objects(client, args.source)
        temp_count = count_objects(client, temp_name)
        print(f"Verification counts after stage copy: source={src_count}, temp={temp_count}")

        if temp_count < src_count:
            raise RuntimeError("Refusing to continue: temporary collection has fewer objects than source.")

        # Step 3: Recreate source collection with snake_case schema
        print(f"Deleting source collection: {args.source}")
        client.collections.delete(args.source)
        print(f"Recreating source collection with snake_case schema: {args.source}")
        create_collection_if_missing(client, args.source, dry_run=False)

        # Step 4: Copy temporary -> source (name is now original again)
        copy_objects(client, temp_name, args.source, dry_run=False)

        # Step 5: Final verification and optional temp cleanup
        final_count = count_objects(client, args.source)
        print(f"Final verification counts: source={final_count}, temp={temp_count}")
        if final_count < temp_count:
            raise RuntimeError("Final source has fewer objects than temporary collection.")

        if args.keep_temp:
            print(f"Keeping temporary collection: {temp_name}")
        else:
            print(f"Deleting temporary collection: {temp_name}")
            client.collections.delete(temp_name)

        print("Migration finished.")

    finally:
        client.close()


if __name__ == "__main__":
    main()