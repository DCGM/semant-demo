import weaviate
import weaviate.classes.config as wvc
from weaviate.classes.init import AdditionalConfig, Timeout

# 1. Nastavení připojení
# Pokud běžíš na localhostu, nechej to takto. 
# Pokud na cloudu, přidej URL a API klíč.
client = weaviate.connect_to_local(
    port=8080,
    grpc_port=50051,
    additional_config=AdditionalConfig(
        timeout=Timeout(init=30, query=60, insert=120) # Pro jistotu delší timeouty
    )
)

def update_schema(collection_name: str):
    try:
        # 2. Získání reference na existující kolekci
        print(f"Připojuji se ke kolekci: {collection_name}...")
        collection = client.collections.get(collection_name)

        # 3. Definice nových vlastností
        # Weaviate v4 umožňuje přidat seznam vlastností
        new_props = [
            wvc.Property(
                name="description",
                data_type=wvc.DataType.TEXT,
                description="Description of the collection"
            ),
            wvc.Property(
                name="createdAt",
                data_type=wvc.DataType.DATE,
                description="Date of creation of the collection"
            ),
            wvc.Property(
                name="updatedAt",
                data_type=wvc.DataType.DATE,
                description="Date of last update of the collection"
            ),
            wvc.Property(
                name="color",
                data_type=wvc.DataType.TEXT, # Hex kód (např. #FF5733)
                description="Color associated with the collection for UI purposes"
            )
        ]

        # 4. Samotné přidání do schématu
        print("Přidávám nové vlastnosti...")
        for prop in new_props:
            collection.config.add_property(prop)
            print(f" - Vlastnost '{prop.name}' přidána.")

        print("\nHotovo! Kolekce byla úspěšně rozšířena.")

    except Exception as e:
        print(f"Chyba při aktualizaci: {e}")
    finally:
        # Vždy zavřít spojení
        client.close()
        
def update_descriptions(collection_name: str):
    try:
        print(f"Připojuji se ke kolekci: {collection_name}...")
        collection = client.collections.get(collection_name)

        collection.config.update(
            property_descriptions={
                "description": "Description of the collection",
                "createdAt": "Date of creation of the collection",
                "updatedAt": "Date of last update of the collection",
                "color": "Color associated with the collection for UI purposes",
                "name": "Name of the collection",
                "user_id": "ID of the user who owns the collection"
            }
        )

    except Exception as e:
        print(f"Chyba při aktualizaci popisů: {e}")
    finally:
        client.close()

# --- SPUŠTĚNÍ ---
# Změň "UserCollection" na reálný název tvé kolekce
if __name__ == "__main__":
    # update_schema("UserCollection")
    update_descriptions("UserCollection")