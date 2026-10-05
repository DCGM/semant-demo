from typing import Optional

import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.config import Configure, Property, DataType, VectorDistances, Vectorizers


def get_async_client(
    host: str = "localhost",
    port: int = 8080,
    grpc_port: int = 50051,
    headers: Optional[dict] = None,
    api_key: Optional[str] = None
) -> weaviate.WeaviateAsyncClient:
    """Create an (not yet connected) async Weaviate client based on parameters.

    Use it as `async with get_async_client(...) as client:` to connect and close it automatically.

    Args:
        host: Weaviate host address.
        port: HTTP/REST port.
        grpc_port: gRPC port.
        headers: Additional HTTP headers.
        api_key: Authentication API key.

    Returns:
        An instantiated WeaviateAsyncClient.
    """
    auth_credentials = None
    if api_key:
        auth_credentials = AuthApiKey(api_key)

    print(f"Connecting to Weaviate at {host}:{port} (gRPC: {grpc_port})...")
    return weaviate.use_async_with_local(
        host=host,
        port=port,
        grpc_port=grpc_port,
        headers=headers,
        auth_credentials=auth_credentials
    )


def build_vector_index_config(index_type: str, distance_metric: str):
    """Build vector index configuration for a new named vector.

    Args:
        index_type: Vector index type (hnsw, flat, dynamic).
        distance_metric: Distance metric (cosine, dot, l2-squared, hamming, manhattan).

    Returns:
        Vector index configuration object.
    """
    try:
        distance = VectorDistances(distance_metric.lower())
    except ValueError:
        raise ValueError(
            f"Unsupported distance metric '{distance_metric}'. "
            f"Supported: {[d.value for d in VectorDistances]}"
        )

    index_types = {
        "hnsw": Configure.VectorIndex.hnsw,
        "flat": Configure.VectorIndex.flat,
        "dynamic": Configure.VectorIndex.dynamic,
    }
    index_factory = index_types.get(index_type.lower())
    if index_factory is None:
        raise ValueError(f"Unsupported vector index type '{index_type}'. Supported: {list(index_types.keys())}")

    return index_factory(distance_metric=distance)


async def ensure_named_vector_exists(
    client: weaviate.WeaviateAsyncClient,
    collection_name: str,
    vector_name: str,
    index_type: str = "hnsw",
    distance_metric: str = "cosine"
) -> None:
    """Ensure a self-provided named vector exists in the collection, creating it on the fly if needed.

    Weaviate allows adding named vectors only to collections that already use named vectors.
    Collections with the legacy (unnamed) vector are refused.

    Args:
        client: The WeaviateAsyncClient.
        collection_name: Name of the collection.
        vector_name: Name of the vector.
        index_type: Vector index type used when the vector is created.
        distance_metric: Distance metric used when the vector is created.
    """
    if not await client.collections.exists(collection_name):
        raise ValueError(f"Collection '{collection_name}' does not exist in Weaviate database.")

    collection = client.collections.use(collection_name)
    schema_config = await collection.config.get()
    named_vectors = schema_config.vector_config or {}

    if vector_name in named_vectors:
        vectorizer = named_vectors[vector_name].vectorizer.vectorizer
        if vectorizer != Vectorizers.NONE:
            raise ValueError(
                f"Named vector '{vector_name}' in collection '{collection_name}' uses vectorizer '{vectorizer}'. "
                f"Only self-provided (vectorizer 'none') vectors can be filled by this tool."
            )
        return

    if not named_vectors:
        raise ValueError(
            f"Collection '{collection_name}' does not use named vectors (it has the legacy unnamed vector). "
            f"Weaviate can add named vectors only to collections created with named vectors, "
            f"so the collection must be migrated first."
        )

    print(f"Named vector '{vector_name}' is missing in collection '{collection_name}'. Creating on the fly...")
    await collection.config.add_vector(
        vector_config=Configure.Vectors.self_provided(
            name=vector_name,
            vector_index_config=build_vector_index_config(index_type, distance_metric)
        )
    )
    print(f"Successfully created named vector '{vector_name}' ({index_type}, {distance_metric}) in collection '{collection_name}'.")


async def create_test_collection(client: weaviate.WeaviateAsyncClient) -> None:
    """Create the EmbedderTest collection (with named vectors) and populate it with 10 Czech historical records.

    Args:
        client: The WeaviateAsyncClient.
    """
    collection_name = "EmbedderTest"

    if await client.collections.exists(collection_name):
        print(f"Collection '{collection_name}' already exists. Deleting it to create a fresh one...")
        await client.collections.delete(collection_name)

    print(f"Creating collection '{collection_name}'...")
    # a collection must be created with at least one named vector to allow adding further named vectors later
    await client.collections.create(
        name=collection_name,
        properties=[
            Property(name="language", data_type=DataType.TEXT),
            Property(name="title", data_type=DataType.TEXT),
            Property(name="text", data_type=DataType.TEXT),
        ],
        vector_config=[Configure.Vectors.self_provided(name="default")]
    )

    print("Populating collection with 10 Czech historical records...")
    records = [
        {"language": "ces", "title": "Kosmova kronika", "text": "Kosmas, děkan kapituly pražské, sepsal na sklonku svého života latinsky psanou kroniku, jež jest nejstarším uceleným popisem dějin našich zemí od věků pradávných až do počátku století dvanáctého."},
        {"language": "ces", "title": "Dalimilova kronika", "text": "Dalimilova kronika, veršované dílo z počátku čtrnáctého věku, poprvé v jazyce českém líčí příběhy slavných knížat a králů naší vlasti, plná lásky k rodné zemi a varování před cizími vlivy."},
        {"language": "ces", "title": "Vita Caroli", "text": "Vita Caroli, vlastní životopis slavného císaře a krále Karla Čtvrtého, vypráví o jeho mládí ve Francii, o návratu do zpustošených Čech i o usilovné snaze obnovit slávu a moc království českého."},
        {"language": "ces", "title": "Dekret kutnohorský", "text": "Václav Čtvrtý podepsal roku čtrnáctistého devátého v Kutné Hoře památný dekret, kterýmžto udělil Čechům tři hlasy na univerzitě pražské, zatímco ostatním národům ponechal pouze hlas jediný."},
        {"language": "ces", "title": "Mistr Jan Hus", "text": "Mistr Jan Hus, kazatel v kapli Betlémské, stál neochvějně za pravdou Boží, pročež byl na sněmu v Kostnici odsouzen a dne šestého července roku čtrnáctistého patnáctého na hranici upálen."},
        {"language": "ces", "title": "Bitva na Bílé hoře", "text": "Dne osmého listopadu roku tisícího šestistého dvacátého strhla se na návrší zvaném Bílá hora bitva krátká, leč pro osud stavovského povstání a celé země české na staletí osudná."},
        {"language": "ces", "title": "Jan Amos Komenský", "text": "Jan Amos Komenský, učitel národů, ve svém Labyrintu světa a ráji srdce mistrně vykreslil marnost lidského pachtění a ukázal, že pravý pokoj lze nalézti pouze ve vnitřním míru a víře."},
        {"language": "ces", "title": "Zlatá bula sicilská", "text": "Zlatá bula sicilská, listina podepsaná římským králem Fridrichem Druhým v Basileji, potvrdila Přemyslu Otakaru Prvnímu dědičný královský titul a vymezila práva a svobody českých panovníků."},
        {"language": "ces", "title": "Kněžna Libuše", "text": "Kněžna Libuše, dcera Krokova, proslula svou moudrostí a věšteckým duchem; z výšiny vyšehradské spatřila město veliké, jehož sláva se měla dotýkat hvězd, a založila tak Prahu."},
        {"language": "ces", "title": "František Palacký", "text": "František Palacký, učenec a otec národa, zasvětil svůj život sepsání velkolepého díla o dějinách národu českého v Čechách i v Moravě, ukazujíc zápas slovanské svobody s tlakem cizím."},
    ]

    collection = client.collections.use(collection_name)
    response = await collection.data.insert_many(records)
    if response.has_errors:
        raise RuntimeError(f"Failed to insert test records: {response.errors}")

    print(f"Successfully created and populated collection '{collection_name}' with {len(records)} records.")
