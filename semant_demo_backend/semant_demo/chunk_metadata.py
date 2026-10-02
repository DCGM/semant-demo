import logging
from pathlib import Path
from typing import Any, Union

import yaml


def load_chunk_metadata_whitelist(config_path: Union[str, Path]) -> set[str]:
    """
    Loads the set of Chunk property names (from Weaviate) allowed to be exposed
    as TextChunk.metadata. The whitelist is defined externally in a YAML file
    (a flat list of property names) rather than in code.
    """
    path = Path(config_path)
    if not path.exists():
        logging.warning(f"Chunk metadata whitelist config not found at {path}, no chunk metadata will be exposed")
        return set()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        logging.warning(f"Chunk metadata whitelist config at {path} is empty, no chunk metadata will be exposed")
        return set()

    return set(data)


def extract_chunk_metadata(properties: dict[str, Any], whitelist: set[str]) -> dict[str, Any]:
    """
    Pops whitelisted keys present in `properties` into a separate metadata dict,
    leaving `properties` with only the remaining (non-metadata) keys.
    """
    return {key: properties.pop(key) for key in whitelist if key in properties}
