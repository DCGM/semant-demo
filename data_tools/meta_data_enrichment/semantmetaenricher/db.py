from typing import Any, Dict, List, Optional
import weaviate
from weaviate.auth import AuthApiKey
from weaviate.classes.config import Property, DataType
from weaviate.classes.query import Filter

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


def ensure_property_exists(
    client: weaviate.WeaviateClient,
    collection_name: str,
    prop_name: str,
    prop_type: str
) -> None:
    """Ensure a property exists in the collection schema, creating it on the fly if needed.
    
    Args:
        client: The WeaviateClient.
        collection_name: Name of the collection.
        prop_name: Name of the property.
        prop_type: Datatype (e.g. text, int, number, boolean, date).
    """
    if not client.collections.exists(collection_name):
        raise ValueError(f"Collection '{collection_name}' does not exist in Weaviate database.")
        
    collection = client.collections.get(collection_name)
    schema_config = collection.config.get()
    
    existing_properties = {prop.name for prop in schema_config.properties}
    if prop_name in existing_properties:
        return
        
    print(f"Property '{prop_name}' is missing in collection '{collection_name}'. Creating on the fly...")
    
    type_mapping = {
        "text": DataType.TEXT,
        "int": DataType.INT,
        "number": DataType.NUMBER,
        "boolean": DataType.BOOL,
        "date": DataType.DATE,
        "text[]": DataType.TEXT_ARRAY,
        "int[]": DataType.INT_ARRAY,
        "number[]": DataType.NUMBER_ARRAY,
        "boolean[]": DataType.BOOL_ARRAY,
    }
    
    data_type = type_mapping.get(prop_type.lower())
    if not data_type:
        raise ValueError(
            f"Unsupported property type '{prop_type}'. "
            f"Supported: {list(type_mapping.keys())}"
        )
        
    prop_obj = Property(name=prop_name, data_type=data_type)
    collection.config.add_property(prop_obj)
    print(f"Successfully created property '{prop_name}' with type '{data_type}' in collection '{collection_name}'.")


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
            weaviate_filters.append(prop_filter.is_none(bool(value)))
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


def create_test_collection(client: weaviate.WeaviateClient) -> None:
    """Create the MetaDataEnrichmentTest collection in Weaviate and populate it with 10 Czech historical records.
    
    Args:
        client: The WeaviateClient.
    """
    collection_name = "MetaDataEnrichmentTest"
    
    # 1. Delete if it already exists to guarantee idempotency
    if client.collections.exists(collection_name):
        print(f"Collection '{collection_name}' already exists. Deleting it to create a fresh one...")
        client.collections.delete(collection_name)
        
    # 2. Create the collection
    print(f"Creating collection '{collection_name}'...")
    
    # Weaviate automatically converts property names starting with uppercase letters to lowercase.
    # We declare properties "language", and "text" to match user requirements.
    properties = [
        Property(name="language", data_type=DataType.TEXT),
        Property(name="text", data_type=DataType.TEXT),
    ]
    
    client.collections.create(
        name=collection_name,
        properties=properties
    )
    
    # 3. Populate it with 10 records
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
    with collection.batch.dynamic() as batch:
        for record in records:
            batch.add_object(properties=record)
            
    print(f"Successfully created and populated collection '{collection_name}' with {len(records)} records.")
