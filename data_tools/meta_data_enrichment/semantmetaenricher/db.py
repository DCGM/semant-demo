from typing import Any, Dict, List, Optional
import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.config import Property, DataType, Tokenization
from weaviate.classes.query import Filter
from weaviate.exceptions import WeaviateUnsupportedFeatureError

def get_client(
    host: str = "localhost",
    port: int = 8080,
    grpc_port: int = 50051,
    headers: Optional[dict] = None,
    api_key: Optional[str] = None
) -> weaviate.WeaviateClient:
    """Create a Weaviate client based on parameters.
    
    Args:
        host: Weaviate host address.
        port: HTTP/REST port.
        grpc_port: gRPC port.
        headers: Additional HTTP headers.
        api_key: Authentication API key.
        
    Returns:
        An instantiated WeaviateClient.
    """
    auth_credentials = None
    if api_key:
        auth_credentials = AuthApiKey(api_key)
        
    print(f"Connecting to Weaviate at {host}:{port} (gRPC: {grpc_port})...")
    return weaviate.connect_to_local(
        host=host,
        port=port,
        grpc_port=grpc_port,
        headers=headers,
        auth_credentials=auth_credentials
    )


PROVENANCE = "classification_provenance"
"""The chunk's classification status (#590): ``UNPROCESSED`` until classified, then the
configured model/version identifier. Declared by the backend's
``classification_provenance_schema``; this tool never declares it on a real store."""
UNPROCESSED = "UNPROCESSED"
TEST_COLLECTION = "MetaDataEnrichmentTest"


class Refused(ValueError):
    """The store or the configuration does not allow a run; nothing was written."""


def resolve_collection(client: weaviate.WeaviateClient, name: str) -> str:
    """The collection an alias points to, or ``name`` itself (schema reads need the real name)."""
    try:
        alias = client.alias.get(alias_name=name)
    except WeaviateUnsupportedFeatureError:  # before Weaviate 1.32: no aliases
        alias = None
    return alias.collection if alias else name


def check_schema(client: weaviate.WeaviateClient, collection_name: str, fields: List[str]) -> str:
    """Refuse (``Refused``) a missing collection, a missing or non-``text[]`` mapped field and a
    missing or differently declared ``classification_provenance`` (``text``, ``field``
    tokenization, filterable). Reads the schema only; returns the resolved collection name."""
    resolved = resolve_collection(client, collection_name)
    if not client.collections.exists(resolved):
        raise Refused(f"Collection '{collection_name}' does not exist in the Weaviate database.")
    declared = {p.name: p for p in client.collections.get(resolved).config.get().properties}
    problems = []
    for name in fields:
        prop = declared.get(name)
        if prop is None:
            problems.append(f"field '{name}' is not declared")
        elif prop.data_type.value != "text[]":
            problems.append(f"field '{name}' is {prop.data_type.value}, expected text[]")
    prop = declared.get(PROVENANCE)
    if prop is None:
        problems.append(f"'{PROVENANCE}' is not declared (declare it with the backend's "
                        "classification_provenance_schema --apply)")
    elif (prop.data_type.value, prop.tokenization.value if prop.tokenization else None,
          bool(prop.index_filterable)) != ("text", "field", True):
        problems.append(f"'{PROVENANCE}' is not declared as text with field tokenization, filterable")
    if problems:
        raise Refused(f"Collection '{resolved}': " + "; ".join(problems) + ". The schema is never changed by a run.")
    return resolved


def build_weaviate_filters(filters_list: List[Dict[str, Any]]) -> Optional[Any]:
    """Build Weaviate Filter object from a list of dict filters.
    
    Args:
        filters_list: List of filter configurations, e.g.:
            [{'property': 'field', 'operator': 'equal', 'value': 'val'}]
            
    Returns:
        A combined Weaviate Filter object, or None if the list is empty.
    """
    if not filters_list:
        return None
        
    weaviate_filters = []
    for f in filters_list:
        prop_name = f.get("property")
        if not prop_name:
            continue
            
        operator = f.get("operator", "equal").lower()
        value = f.get("value")
        
        prop_filter = Filter.by_property(prop_name)
        
        if operator == "equal":
            weaviate_filters.append(prop_filter.equal(value))
        elif operator == "not_equal":
            weaviate_filters.append(prop_filter.not_equal(value))
        elif operator == "greater_than":
            weaviate_filters.append(prop_filter.greater_than(value))
        elif operator == "less_than":
            weaviate_filters.append(prop_filter.less_than(value))
        elif operator == "greater_or_equal":
            weaviate_filters.append(prop_filter.greater_or_equal(value))
        elif operator == "less_or_equal":
            weaviate_filters.append(prop_filter.less_or_equal(value))
        elif operator == "is_none":
            # Cast value to bool (e.g. True to filter for is_none, False for is_not_none)
            weaviate_filters.append(prop_filter.is_none(bool(value)))  # FIXME: value should be a boolean on the user side, but we cast it here just in case - we should validate this in the config schema instead
        elif operator == "contains_any":
            weaviate_filters.append(prop_filter.contains_any(value))
        elif operator == "contains_all":
            weaviate_filters.append(prop_filter.contains_all(value))
        elif operator == "contains_none":
            weaviate_filters.append(prop_filter.contains_none(value))
        elif operator == "like":
            weaviate_filters.append(prop_filter.like(value))
        else:
            raise ValueError(f"Unsupported filter operator: '{operator}'")
            
    if not weaviate_filters:
        return None
        
    if len(weaviate_filters) == 1:
        return weaviate_filters[0]
        
    return Filter.all_of(weaviate_filters)


def create_test_collection(client: weaviate.WeaviateClient, fields: List[str], replace: bool = False,
                           collection_name: str = TEST_COLLECTION) -> None:
    """Create the MetaDataEnrichmentTest collection and populate it with 10 Czech historical records.

    The collection declares ``language``, ``text``, the mapped ``fields`` (``text[]``) and
    ``classification_provenance`` as the backend's schema command does; every record is
    ``UNPROCESSED``, so a run selects all of them.

    Args:
        client: The WeaviateClient.
        fields: The mapped classification fields (the keys of ``field_tasks``).
        replace: Delete an existing collection of that name first. Without it, an existing
            collection is refused (``Refused``) and left unchanged.
        collection_name: Name of the created collection.
    """
    if client.collections.exists(collection_name):
        if not replace:
            raise Refused(f"Collection '{collection_name}' already exists. It was left unchanged; "
                          f"use --force to delete it and create it again.")
        print(f"Collection '{collection_name}' already exists. Deleting it (--force) to create a fresh one...")
        client.collections.delete(collection_name)

    print(f"Creating collection '{collection_name}'...")
    client.collections.create(
        name=collection_name,
        properties=[
            Property(name="language", data_type=DataType.TEXT),
            Property(name="text", data_type=DataType.TEXT),
            *(Property(name=name, data_type=DataType.TEXT_ARRAY) for name in fields),
            Property(name=PROVENANCE, data_type=DataType.TEXT, tokenization=Tokenization.FIELD,
                     index_filterable=True, index_searchable=False),
        ]
    )

    print("Populating collection with 10 Czech historical records...")

    records = [
        {
            "language": "ces",
            "text": "Kosmas, děkan kapituly pražské, sepsal na sklonku svého života latinsky psanou kroniku, jež jest nejstarším uceleným popisem dějin našich zemí od věků pradávných až do počátku století dvanáctého."
        },
        {
            "language": "ces",
            "text": "Dalimilova kronika, veršované dílo z počátku čtrnáctého věku, poprvé v jazyce českém líčí příběhy slavných knížat a králů naší vlasti, plná lásky k rodné zemi a varování před cizími vlivy."
        },
        {
            "language": "ces",
            "text": "Vita Caroli, vlastní životopis slavného císaře a krále Karla Čtvrtého, vypráví o jeho mládí ve Francii, o návratu do zpustošených Čech i o usilovné snaze obnovit slávu a moc království českého."
        },
        {
            "language": "ces",
            "text": "Václav Čtvrtý podepsal roku čtrnáctistého devátého v Kutné Hoře památný dekret, kterýmžto udělil Čechům tři hlasy na univerzitě pražské, zatímco ostatním národům ponechal pouze hlas jediný."
        },
        {
            "language": "ces",
            "text": "Mistr Jan Hus, kazatel v kapli Betlémské, stál neochvějně za pravdou Boží, pročež byl na sněmu v Kostnici odsouzen a dne šestého července roku čtrnáctistého patnáctého na hranici upálen."
        },
        {
            "language": "ces",
            "text": "Dne osmého listopadu roku tisícího šestistého dvacátého strhla se na návrší zvaném Bílá hora bitva krátká, leč pro osud stavovského povstání a celé země české na staletí osudná."
        },
        {
            "language": "ces",
            "text": "Jan Amos Komenský, učitel národů, ve svém Labyrintu světa a ráji srdce mistrně vykreslil marnost lidského pachtění a ukázal, že pravý pokoj lze nalézti pouze ve vnitřním míru a víře."
        },
        {
            "language": "ces",
            "text": "Zlatá bula sicilská, listina podepsaná římským králem Fridrichem Druhým v Basileji, potvrdila Přemyslu Otakaru Prvnímu dědičný královský titul a vymezila práva a svobody českých panovníků."
        },
        {
            "language": "ces",
            "text": "Kněžna Libuše, dcera Krokova, proslula svou moudrostí a věšteckým duchem; z výšiny vyšehradské spatřila město veliké, jehož sláva se měla dotýkat hvězd, a založila tak Prahu."
        },
        {
            "language": "ces",
            "text": "František Palacký, učenec a otec národa, zasvětil svůj život sepsání velkolepého díla o dějinách národu českého v Čechách i v Moravě, ukazujíc zápas slovanské svobody s tlakem cizím."
        }
    ]
    
    collection = client.collections.get(collection_name)
    response = collection.data.insert_many([{**record, PROVENANCE: UNPROCESSED} for record in records])
    if response.has_errors:
        raise RuntimeError(f"Failed to insert test records: {response.errors}")

    print(f"Successfully created and populated collection '{collection_name}' with {len(records)} records.")
