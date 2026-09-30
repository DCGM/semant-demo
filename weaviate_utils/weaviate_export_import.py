# Transfer 50 documents and their chunks from prod DB (port 8080) to test DB (port 8082).
# Preserves all properties, vectors, UUIDs, and cross-references.
import requests

PROD_URL = "http://localhost:8080"
TEST_URL = "http://localhost:8082"

PROD_DOC_CLASS = "Documents_test"
PROD_CHUNK_CLASS = "Chunks_test"
DOC_CLASS = "Documents"
CHUNK_CLASS = "Chunks"
DOC_LIMIT = 50


def get_all_objects(base_url, class_name, include_vector=False):
    objects = []
    vector_param = "&include=vector" if include_vector else ""
    url = f"{base_url}/v1/objects?class={class_name}&limit=500{vector_param}"
    batch_count = 0
    while True:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("objects", [])
        if not batch:
            break
        objects.extend(batch)
        batch_count += 1
        print(f"  [Batch {batch_count}] Načteno {len(objects)} objektů...")
        if len(batch) < 500:
            break
        url = f"{base_url}/v1/objects?class={class_name}&limit=500{vector_param}&after={batch[-1]['id']}"
    return objects


def delete_all_in_class(base_url, class_name):
    deleted = 0
    while True:
        resp = requests.get(f"{base_url}/v1/objects?class={class_name}&limit=250")
        resp.raise_for_status()
        objs = resp.json().get("objects", [])
        if not objs:
            break
        for obj in objs:
            requests.delete(f"{base_url}/v1/objects/{class_name}/{obj['id']}").raise_for_status()
            deleted += 1
    print(f"Smazáno {deleted} objektů třídy {class_name}.")


# 0a. Zkopíruj schéma z produkce do testovací DB (chybějící třídy, přejmenuj _test -> bez suffixu)
print("Synchronizuji schéma z produkční DB do testovací DB...")
prod_schema = requests.get(f"{PROD_URL}/v1/schema").json()
test_schema = requests.get(f"{TEST_URL}/v1/schema").json()
test_classes = {c["class"] for c in test_schema.get("classes", [])}

def strip_test_suffix(name: str) -> str:
    return name[:-5] if name.endswith("_test") else name

def is_cross_ref(prop):
    return any(dt[0].isupper() for dt in prop.get("dataType", []))

READONLY_SHARD_FIELDS = {"actualCount", "actualVirtualCount"}

cross_refs_to_add = []

for cls in prod_schema.get("classes", []):
    new_class_name = strip_test_suffix(cls["class"])
    if new_class_name not in test_classes:
        cls_create = {k: v for k, v in cls.items()}
        cls_create["class"] = new_class_name

        if "shardingConfig" in cls_create:
            cls_create["shardingConfig"] = {
                k: v for k, v in cls_create["shardingConfig"].items()
                if k not in READONLY_SHARD_FIELDS
            }

        all_props = cls_create.get("properties", [])
        cls_create["properties"] = [p for p in all_props if not is_cross_ref(p)]
        for p in all_props:
            if is_cross_ref(p):
                # Přejmenuj i dataType reference
                p_copy = dict(p)
                p_copy["dataType"] = [strip_test_suffix(dt) for dt in p["dataType"]]
                cross_refs_to_add.append((new_class_name, p_copy))

        resp = requests.post(f"{TEST_URL}/v1/schema", json=cls_create)
        if not resp.ok:
            print(f"  Chyba při vytváření třídy {new_class_name}: {resp.text}")
        else:
            print(f"  Vytvořena třída: {cls['class']}")
    else:
            print(f"  Třída již existuje: {new_class_name}")
# Přidej cross-reference properties až když všechny třídy existují
for class_name, prop in cross_refs_to_add:
    resp = requests.post(f"{TEST_URL}/v1/schema/{class_name}/properties", json=prop)
    if not resp.ok:
        print(f"  Chyba při přidávání property {prop['name']} do {class_name}: {resp.text}")
    else:
        print(f"  Přidána cross-ref property {prop['name']} do {class_name}")

# 0b. Smaž existující data v testovací DB
print("Mažu existující data v testovací DB...")
delete_all_in_class(TEST_URL, CHUNK_CLASS)
delete_all_in_class(TEST_URL, DOC_CLASS)

# 1. Získej 150 dokumentů z produkční DB (všechna pole + vektory)
print(f"Načítám {DOC_LIMIT} dokumentů z produkční DB...")
resp = requests.get(f"{PROD_URL}/v1/objects?class={PROD_DOC_CLASS}&limit={DOC_LIMIT}&include=vector")
resp.raise_for_status()
docs = resp.json().get("objects", [])
print(f"Načteno {len(docs)} dokumentů.")

doc_ids = {doc["id"] for doc in docs}

# 2. Načti chunky pro vybrané dokumenty (GraphQL s filtrováním)
print("Načítám chunky z produkční DB (filtrováním)...")
chunks_to_import = []

# Pro efektivitu: namísto iterace všech chunků, iteruj dokumenty a hledej jejich chunky
for i, doc in enumerate(docs):
    if i % 50 == 0:
        print(f"  Zpracováno {i}/{len(docs)} dokumentů...")
    
    # GraphQL query na chunky tohoto dokumentu
    query = {
        "query": f"""
        {{
            Get {{
                {PROD_CHUNK_CLASS}(where: {{
                    path: ["document", "{PROD_DOC_CLASS}", "id"],
                    operator: Equal,
                    valueString: "{doc['id']}"
                }}) {{
                    _additional {{ id }}
                    text
                    from_page
                    to_page
                    language
                    start_page_id
                    end_paragraph
                    document {{ ... on {PROD_DOC_CLASS} {{ _additional {{ id }} }} }}
                }}
            }}
        }}
        """
    }
    
    resp = requests.post(f"{PROD_URL}/v1/graphql", json=query)
    if resp.ok:
        doc_chunks = resp.json().get("data", {}).get("Get", {}).get(PROD_CHUNK_CLASS, [])
        chunks_to_import.extend(doc_chunks)

print(f"Chunků k importu: {len(chunks_to_import)}")

# 3. Importuj dokumenty (zachovat UUID, pole, vektor)
print("Importuji dokumenty do testovací DB...")
for i, doc in enumerate(docs):
    props = dict(doc.get("properties", {}))
    # Odstraň cross-references na objekty mimo scope
    props.pop("collection", None)
    
    obj = {"id": doc["id"], "class": DOC_CLASS, "properties": props}
    if doc.get("vector"):
        obj["vector"] = doc["vector"]
    resp = requests.post(f"{TEST_URL}/v1/objects", json=obj)
    if not resp.ok:
        print(f"  Chyba u dokumentu {i}: {resp.status_code} {resp.text}")
        break
    if i % 50 == 0:
        print(f"  Importováno {i}/{len(docs)} dokumentů...")
print(f"Importováno {len(docs)} dokumentů.")

# 4. Importuj chunky (zachovat UUID, pole, vektor a referenci na dokument)
print("Importuji chunky do testovací DB...")
for i, chunk in enumerate(chunks_to_import):
    chunk_id = chunk.get("_additional", {}).get("id")
    if not chunk_id:
        continue
    
    # Stáhni VŠECHNY properties + vektor z produkce přes REST (GraphQL vrací jen vyžádaná pole)
    vec_resp = requests.get(f"{PROD_URL}/v1/objects/{PROD_CHUNK_CLASS}/{chunk_id}?include=vector")
    if not vec_resp.ok:
        continue
    full_obj = vec_resp.json()
    vector = full_obj.get("vector")
    props = dict(full_obj.get("properties", {}))
    
    # Odstraň cross-reference properties kromě document
    props.pop("userCollection", None)
    props.pop("automaticTag", None)
    props.pop("positiveTag", None)
    props.pop("negativeTag", None)
    
    # Převeď document referenci: Documents_test -> Documents (beacon z REST je jiný formát než GraphQL)
    # GraphQL fallback: pokud REST nevrátil document ref, použij ho z GraphQL
    doc_ref_from_graphql = chunk.get("document")
    if "document" in props and props["document"]:
        # REST vrací beacony ve tvaru weaviate://localhost/Documents_test/uuid
        beacon_refs = []
        for ref in (props["document"] or []):
            beacon = ref.get("beacon", "")
            # extrahuj UUID (poslední část beaconu)
            ref_id = beacon.split("/")[-1] if beacon else None
            if ref_id:
                beacon_refs.append({"beacon": f"weaviate://localhost/{DOC_CLASS}/{ref_id}"})
        props["document"] = beacon_refs if beacon_refs else None
    elif doc_ref_from_graphql:
        # Fallback: použij referenci z GraphQL
        beacon_refs = []
        for ref in (doc_ref_from_graphql or []):
            ref_id = ref.get("_additional", {}).get("id") if isinstance(ref, dict) else None
            if ref_id:
                beacon_refs.append({"beacon": f"weaviate://localhost/{DOC_CLASS}/{ref_id}"})
        props["document"] = beacon_refs if beacon_refs else None
    
    obj = {"id": chunk_id, "class": CHUNK_CLASS, "properties": props}
    if vector:
        obj["vector"] = vector
    resp = requests.post(f"{TEST_URL}/v1/objects", json=obj)
    if not resp.ok:
        print(f"  Chyba u chunku {i}: {resp.status_code} {resp.text}")
        break
print(f"Importováno {len(chunks_to_import)} chunků.")
print("Hotovo!")