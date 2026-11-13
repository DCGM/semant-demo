"""Classify the chunks that await classification (#590).

A run selects the chunks whose ``classification_provenance`` is ``UNPROCESSED`` (narrowed by the
configured ``filters``), asks the model only for the mapped fields a chunk is missing (absent,
``null`` or ``[]``) and, when every missing field got a valid result, writes those fields and the
configured ``provenance`` identifier in one update. Existing non-empty values are never
overwritten. A chunk that fails is not written and stays ``UNPROCESSED``; the next run retries
it. Chunks without a ``classification_provenance`` value are never selected.

The stored status is the state: there is no checkpoint. Every page is the first page of the
remaining selection (classified chunks leave it, chunks that failed in this run are excluded),
so no chunk is skipped by offset paging and no query reaches Weaviate's
``QUERY_MAXIMUM_RESULTS``; ``max_failures`` bounds the excluded ids. The schema is only read:
a missing collection, mapped field or ``classification_provenance`` property refuses the run.
"""
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from classconfig import ConfigurableMixin, CreatableMixin, ConfigurableValue, ConfigurableSubclassFactory
from tqdm import tqdm
from weaviate.classes.query import Filter

from .db import PROVENANCE, UNPROCESSED, Refused, build_weaviate_filters, check_schema, get_client
# Import models to register their subclasses for ConfigurableSubclassFactory
from .models import Model, LocalHFClassifierModel


def valid_provenance(value: Any) -> bool:
    """A non-empty identifier without surrounding whitespace, other than ``UNPROCESSED``."""
    return isinstance(value, str) and bool(value) and value == value.strip() and value != UNPROCESSED


def is_missing(value: Any) -> bool:
    """A classification field that a run computes: absent, ``null`` or ``[]``."""
    return value is None or value == []


@dataclass
class RunResult:
    """The outcome of a run or a check, printed as the JSON summary."""
    collection: str
    provenance: str
    selected: int = 0  # UNPROCESSED chunks matching the filters at the start
    classified: int = 0  # chunks written with the provenance
    filled: int = 0  # missing fields written
    failed: list[str] = field(default_factory=list)  # ids of chunks that failed in this run
    remaining: Optional[int] = None  # UNPROCESSED chunks matching the filters at the end
    stopped: Optional[str] = None  # why the run stopped before the selection was exhausted
    refused: Optional[str] = None  # why the run or the check was refused (nothing written)
    model: Optional[dict] = None  # the model's fingerprint (runs only)

    def exit_code(self) -> int:
        """0 when nothing selected is left UNPROCESSED, 1 when chunks remain, 2 when refused."""
        if self.refused:
            return 2
        return 1 if self.stopped or self.remaining else 0


class EnrichmentPipeline(ConfigurableMixin, CreatableMixin):
    """A configurable pipeline that classifies the chunks awaiting classification and writes the
    missing classification fields and the provenance identifier.
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
        desc="Name of the Weaviate collection (or alias) to classify",
        user_default="Chunks"
    )
    provenance: str = ConfigurableValue(
        desc="Model/version identifier written to classification_provenance of every classified chunk "
             "(e.g. mmbert-multitask-2026-07-15). Required; change it whenever the model changes. "
             "UNPROCESSED is refused",
        user_default=None,
        validator=valid_provenance
    )

    # Pipeline execution settings
    field_tasks: dict = ConfigurableValue(
        desc="Non-empty mapping of Weaviate property names (keys, declared as text[]) to their classification task "
             "names (values)",
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
        },
        validator=lambda v: isinstance(v, dict) and len(v) > 0
    )
    filters: list = ConfigurableValue(
        desc="List of query filters that further narrow the UNPROCESSED chunks; never on a mapped field or classification_provenance.",
        user_default=[],
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
    max_consecutive_failures: int = ConfigurableValue(
        desc="Stop after this many consecutive chunks failed (e.g. an unreachable model); they stay UNPROCESSED",
        user_default=10,
        validator=lambda v: isinstance(v, int) and v > 0
    )
    max_failures: int = ConfigurableValue(
        desc="Stop after this many chunks failed in a run (they stay UNPROCESSED); bounds the failed ids "
             "excluded from every query and listed in the summary",
        user_default=1000,
        validator=lambda v: isinstance(v, int) and v > 0
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
        desc="Model configuration (local HF transformers or OpenAI-compatible API)",
        user_default=LocalHFClassifierModel
    )

    def _client(self):
        return get_client(host=self.weaviate_host, port=self.weaviate_port, grpc_port=self.weaviate_grpc_port,
                          headers=self.weaviate_headers, api_key=self.weaviate_api_key)

    def _check_config(self) -> None:
        if not valid_provenance(self.provenance):
            raise Refused(f"provenance must be a non-empty identifier other than {UNPROCESSED}, got {self.provenance!r}")
        written = set(self.field_tasks) | {PROVENANCE}
        filtered = {f.get("property") for f in self.filters or []}
        if filtered & written:
            raise Refused(f"Filters cannot include properties a run writes: {sorted(filtered & written)}")

    def _selection(self, failed: list[str] = ()) -> Filter:
        """The UNPROCESSED chunks matching the configured filters, without ``failed``."""
        parts = [Filter.by_property(PROVENANCE).equal(UNPROCESSED)]
        configured = build_weaviate_filters(self.filters)
        if configured is not None:
            parts.append(configured)
        if failed:
            parts.append(Filter.by_id().contains_none(list(failed)))
        return Filter.all_of(parts) if len(parts) > 1 else parts[0]

    def _prepare(self, client) -> tuple[Any, RunResult]:
        """Check the configuration and the schema; ``Refused`` before anything is written."""
        self._check_config()
        resolved = check_schema(client, self.collection, list(self.field_tasks))
        result = RunResult(collection=resolved, provenance=self.provenance)
        collection = client.collections.get(resolved)
        result.selected = collection.aggregate.over_all(total_count=True, filters=self._selection()).total_count
        return collection, result

    def check(self) -> RunResult:
        """Read-only: refusals and the number of chunks a run would select. Loads no model."""
        client = self._client()
        try:
            try:
                _, result = self._prepare(client)
            except Refused as e:
                return RunResult(collection=self.collection, provenance=self.provenance, refused=str(e))
            result.remaining = result.selected
            return result
        finally:
            client.close()

    def run(self) -> RunResult:
        """Classify the selection; see the module docstring."""
        client = self._client()
        try:
            try:
                collection, result = self._prepare(client)
            except Refused as e:
                return RunResult(collection=self.collection, provenance=self.provenance, refused=str(e))
            with self.model:
                labels = {task: self.model.labels(task) for task in set(self.field_tasks.values())}
                unknown = sorted(task for task, classes in labels.items() if not classes)
                if unknown:
                    result.refused = f"The model has no classes for the task(s) {unknown}"
                    return result
                result.model = self.model.fingerprint()
                self._classify(collection, labels, result)
            result.remaining = collection.aggregate.over_all(total_count=True, filters=self._selection()).total_count
            return result
        finally:
            client.close()

    def _classify(self, collection, labels: dict[str, list[str]], result: RunResult) -> None:
        print(f"Classifying {result.selected} UNPROCESSED chunks of '{result.collection}' as '{self.provenance}'...")
        pbar = tqdm(total=result.selected, desc="Classifying chunks")
        max_rec = self.max_records or 0
        processed = consecutive = 0
        try:
            while True:
                limit = self.batch_size if max_rec <= 0 else min(self.batch_size, max_rec - processed)
                if limit <= 0:
                    # A run whose max_records exactly exhausts the selection is complete, not stopped.
                    if collection.query.fetch_objects(filters=self._selection(result.failed), limit=1).objects:
                        result.stopped = f"max_records ({max_rec}) reached"
                    break
                page = collection.query.fetch_objects(filters=self._selection(result.failed), limit=limit).objects
                if not page:
                    break
                for obj, update in zip(page, self._compute(page, labels)):
                    ok = update is not None and self._write(collection, obj.uuid, update)
                    processed += 1
                    pbar.update(1)
                    if ok:
                        result.classified += 1
                        result.filled += len(update) - 1
                        consecutive = 0
                        continue
                    result.failed.append(str(obj.uuid))
                    consecutive += 1
                    if consecutive >= self.max_consecutive_failures:
                        result.stopped = f"{consecutive} consecutive chunks failed"
                        return
                    if len(result.failed) >= self.max_failures:
                        result.stopped = f"max_failures ({self.max_failures}) reached"
                        return
        finally:
            pbar.close()

    def _compute(self, page: list, labels: dict[str, list[str]]) -> list[Optional[dict]]:
        """Per chunk: the properties to write (the computed missing fields and the provenance),
        or None when a missing field got no valid result. The model is asked once per set of
        missing fields, only for those fields' tasks."""
        missing = [tuple(name for name in self.field_tasks if is_missing(obj.properties.get(name))) for obj in page]
        updates: list[Optional[dict]] = [None] * len(page)
        for fields in dict.fromkeys(missing):
            members = [i for i, m in enumerate(missing) if m == fields]
            tasks = list(dict.fromkeys(self.field_tasks[name] for name in fields))
            records = [{k: (v if v is not None else "") for k, v in page[i].properties.items()} for i in members]
            predictions = self.model.generate_batch(records, tasks) if tasks else [{} for _ in members]
            for i, predicted in zip(members, predictions):
                update = {}
                for name in fields:
                    value = predicted.get(self.field_tasks[name])
                    allowed = labels[self.field_tasks[name]]
                    if not (isinstance(value, list) and value and all(v in allowed for v in value)):
                        print(f"\n[Warning] Chunk {page[i].uuid}: no valid result for '{name}' ({value!r}); not written.")
                        break
                    update[name] = list(value)
                else:
                    updates[i] = {**update, PROVENANCE: self.provenance}
        return updates

    def _write(self, collection, uuid, properties: dict) -> bool:
        """One update (a merge of ``properties``), retried on errors; False when it kept failing."""
        retries = 0
        while True:
            try:
                collection.data.update(uuid=uuid, properties=properties)
                return True
            except Exception as e:
                if retries >= self.max_retries:
                    print(f"\n[Error] Database update failed for record {uuid} after {self.max_retries} retries: {e}")
                    return False
                retries += 1
                print(f"\n[Warning] Database update failed for record {uuid}: {e}. Retrying in {self.retry_delay}s... "
                      f"(Attempt {retries}/{self.max_retries})")
                time.sleep(self.retry_delay)
