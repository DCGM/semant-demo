import weaviate
import weaviate.classes.query as wm

client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
)

try:
    # Získání kolekce
    collection = client.collections.get("UserCollection")

    # Smazání všech objektů, kde ID existuje (tedy všech)
    result = collection.data.delete_many(
        where=wm.Filter.by_property("name").like("*")
    )

    print(f"Smazáno záznamů: {result.successful}")

finally:
    client.close()
