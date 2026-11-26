"""What dataset and run manifests leave out: where things run and local paths.

Manifests travel with datasets and runs, which may be shared (dataset summaries, reports on
issues). They record what was run (models, prompts, settings, hashes), never where: host names,
URLs of model or embedding servers, the store's host and local paths (the token file, the
configuration, imported files). A configuration's SHA-256 still identifies the exact file used.
"""
from typing import Any

PRIVATE_KEYS = frozenset({"host", "base_url", "model_endpoint", "endpoint", "token_file", "path"})
NOT_RECORDED = "<not recorded>"


def shareable(value: Any) -> Any:
    """``value`` with every ``PRIVATE_KEYS`` entry, at any depth, replaced by ``NOT_RECORDED``."""
    if isinstance(value, dict):
        return {k: (NOT_RECORDED if k in PRIVATE_KEYS and v is not None else shareable(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [shareable(v) for v in value]
    return value
