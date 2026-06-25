from typing import Optional

from classconfig import ConfigurableMixin, CreatableMixin, ConfigurableValue, ConfigurableSubclassFactory
from tqdm import tqdm

from .db import get_client, ensure_property_exists, build_weaviate_filters
# Import models to register their subclasses for ConfigurableSubclassFactory
from .models import Model, LocalHFClassifierModel


class EnrichmentPipeline(ConfigurableMixin, CreatableMixin):
    """A fully configurable pipeline that queries Weaviate database records,
    classifies them for multiple tasks, and updates/creates the defined fields.
    """
    
    # Weaviate connection settings
    weaviate_host: str = ConfigurableValue(
        desc="Weaviate host address",
        user_default="localhost"
    )
    weaviate_port: int = ConfigurableValue(
        desc="Weaviate HTTP/REST port",
        user_default=8080
    )
    weaviate_grpc_port: int = ConfigurableValue(
        desc="Weaviate gRPC port (required for client v4)",
        user_default=50051
    )
    weaviate_api_key: Optional[str] = ConfigurableValue(
        desc="Authentication API Key for Weaviate instance",
        user_default=None,
        voluntary=True
    )
    weaviate_headers: Optional[dict] = ConfigurableValue(
        desc="Additional HTTP headers (e.g. API keys for third-party vectorizers)",
        user_default=None,
        voluntary=True
    )
    
    collection: str = ConfigurableValue(
        desc="Name of the Weaviate collection to enrich",
        user_default="Chunks"
    )
    
    # Pipeline execution settings
    field_tasks: dict = ConfigurableValue(
        desc="Mapping of Weaviate property names (keys) to their classification task names (values)",
        user_default={
            "communicative_mode": "communicative_mode",
            "complexity": "complexity",
            "documentary_role": "documentary_role",
            "emotional_tone": "emotional_tone",
            "geographic_scope": "geographic_scope",
            "information_granularity": "information_granularity",
            "intertextual_density": "intertextual_density",
            "named_entity_focus": "named_entity_focus",
            "narrative_perspective": "narrative_perspective",
            "quantitative_content_density": "quantitative_content_density",
            "reliability_signals": "reliability_signals",
            "structural_form": "structural_form",
            "style": "style",
            "subject_domain": "subject_domain",
            "temporal_reference_frame": "temporal_reference_frame",
            "textual_stance": "textual_stance"
        }
    )
    filters: list = ConfigurableValue(
        desc="List of query filters.",
        user_default=[
            {"property": "language", "operator": "Equal", "value": "ces"}
        ],
        voluntary=True
    )
    batch_size: int = ConfigurableValue(
        desc="Number of records to fetch per batch",
        user_default=32
    )
    max_records: Optional[int] = ConfigurableValue(
        desc="Maximum total records to process (None or 0 for unlimited)",
        user_default=None,
        voluntary=True
    )
    
    max_retries: int = ConfigurableValue(
        desc="Maximum number of retries for database updates in case of connection errors",
        user_default=5
    )
    retry_delay: float = ConfigurableValue(
        desc="Delay in seconds between retries",
        user_default=10.0
    )
    
    # Model settings
    model: Model = ConfigurableSubclassFactory(
        parent_cls_type=Model,
        desc="Model configuration (local HF transformers, OpenAI-compatible API, or PyTorch Lightning)",
        user_default=LocalHFClassifierModel
    )

    def run(self) -> None:
        if self.filters:
            # check we don't have destructive filters
            filter_properties = set(f["property"] for f in self.filters)
            fields = set(self.field_tasks.keys())

            if len(filter_properties & fields) > 0:
                raise ValueError("Filters cannot include properties that are being updated in the same pipeline run.")

        """Run the enrichment pipeline."""
        # 1. Connect to Weaviate
        client = get_client(
            host=self.weaviate_host,
            port=self.weaviate_port,
            grpc_port=self.weaviate_grpc_port,
            headers=self.weaviate_headers,
            api_key=self.weaviate_api_key
        )
        
        try:
            # 2. Check and optionally create all output properties on the fly
            for field_name in self.field_tasks.keys():
                ensure_property_exists(
                    client=client,
                    collection_name=self.collection,
                    prop_name=field_name,
                    prop_type="text"
                )
            
            # 3. Get collection and build filters
            collection = client.collections.get(self.collection)
            weaviate_filters = build_weaviate_filters(self.filters)
            
            # 4. Process records in batches
            total_processed = 0
            max_rec = self.max_records or 0
            
            print(f"Starting metadata enrichment pipeline on collection '{self.collection}'...")
            pbar = tqdm(desc="Enriching records")
            
            last_uuid = None
            
            while True:
                # Calculate limit for this batch if max_records is set
                limit = self.batch_size
                if max_rec > 0:
                    remaining = max_rec - total_processed
                    if remaining <= 0:
                        break
                    limit = min(self.batch_size, remaining)
                
                # Fetch objects with cursor pagination
                fetch_kwargs = {
                    "filters": weaviate_filters,
                    "limit": limit
                }

                # pagination
                if weaviate_filters is None:
                    if last_uuid is not None:
                        fetch_kwargs["after"] = last_uuid
                else:
                    # when filters are active we need to fall back to limit offset pagination
                    # however it seems to be rather inefficient: https://docs.weaviate.io/weaviate/api/graphql/additional-operators#performance-considerations
                    fetch_kwargs["offset"] = total_processed
                    
                response = collection.query.fetch_objects(**fetch_kwargs)
                
                if not response.objects:
                    break
                    
                last_uuid = response.objects[-1].uuid
                
                database_records = []
                requested_tasks = list(self.field_tasks.values())
                
                for obj in response.objects:
                    properties = obj.properties
                    database_records.append({k: (v if v is not None else "") for k, v in properties.items()})
                
                # Run model generation for all tasks in batch
                batch_predictions = self.model.generate_batch(database_records, tasks=requested_tasks)
                
                for obj, predictions in zip(response.objects, batch_predictions):
                    
                    # Map predictions to database fields
                    update_properties = {}
                    for field_name, task_name in self.field_tasks.items():
                        generated_val = predictions.get(task_name)
                        if generated_val is not None:
                            update_properties[field_name] = generated_val
                    
                    import time
                    
                    # Save back to Weaviate
                    retries = 0
                    while True:
                        try:
                            collection.data.update(
                                uuid=obj.uuid,
                                properties=update_properties
                            )
                            break
                        except Exception as e:
                            if retries >= self.max_retries:
                                print(f"\n[Error] Database update failed for record {obj.uuid} after {self.max_retries} retries.")
                                raise e
                            retries += 1
                            print(f"\n[Warning] Database update failed for record {obj.uuid}: {e}. Retrying in {self.retry_delay}s... (Attempt {retries}/{self.max_retries})")
                            time.sleep(self.retry_delay)

                    total_processed += 1
                    pbar.update(1)
                        
            pbar.close()
            print(f"Pipeline finished. Successfully enriched {total_processed} records.")
            
        finally:
            client.close()
            print("Weaviate connection closed.")
