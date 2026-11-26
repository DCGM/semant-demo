"""Language codes of the benchmark (ISO 639-3, as the corpus stores them) and their names for prompts."""

NAMES = {"ces": "Czech", "eng": "English", "deu": "German", "slk": "Slovak", "pol": "Polish", "fra": "French",
         "lat": "Latin", "ita": "Italian", "spa": "Spanish", "hun": "Hungarian", "rus": "Russian",
         "ukr": "Ukrainian", "nld": "Dutch"}
DEFAULT = ("ces", "eng", "deu")
"""The languages of dataset v1 (#730): corpus and queries."""


def name(code: str) -> str:
    """The English name of a language for a prompt; the code itself when unknown."""
    return NAMES.get(code, code)
