import logging
from pathlib import Path
from typing import Union

import yaml
from weaviate.classes.aggregate import Metrics

from semant_demo.schemas import (
    FilterType,
    NominalFilterValue,
    SearchFilter,
    SearchFiltersResponse,
    SearchFilterInput,
)
from semant_demo.weaviate_utils.weaviate_abstraction import WeaviateAbstraction

LANGUAGE_MAP = {
    "cs": "Czech", "ces": "Czech", "cze": "Czech",
    "de": "German", "deu": "German", "ger": "German",
    "en": "English", "eng": "English",
    "la": "Latin", "lat": "Latin",
    "hu": "Hungarian", "hun": "Hungarian",
    "sk": "Slovak", "slk": "Slovak", "slo": "Slovak",
    "fr": "French", "fra": "French", "fre": "French",
    "es": "Spanish", "spa": "Spanish",
    "pl": "Polish", "pol": "Polish",
    "ru": "Russian", "rus": "Russian",
    "it": "Italian", "ita": "Italian",
    "zxx": "No linguistic content",
    "mul": "Multiple languages",
    "und": "Undetermined",
}

# Use only as a fallback of a default during config creation, load from config otherwise
TASK_CLASSES = {
    "communicative_mode": [
        "narration", "description", "exposition", "argumentation",
        "instruction", "record", "interaction", "expression", "rhetorics"
    ],
    "complexity": [
        "very_easy", "easy", "moderate", "advanced", "expert"
    ],
    "documentary_role": [
        "journalistic", "scholarly", "literary", "legal", "administrative",
        "religious", "educational", "commercial", "personal",
        "official_public_communication", "reference"
    ],
    "emotional_tone": [
        "neutral_or_detached", "solemn_or_grave", "celebratory_or_triumphant",
        "anxious_or_alarmed", "mournful_or_elegiac", "indignant_or_outraged",
        "hopeful_or_aspirational", "reverent_or_devotional", "ironic_or_sardonic",
        "affectionate_or_tender"
    ],
    "geographic_scope": [
        "hyper_local", "local_or_municipal", "regional", "national",
        "multi_national_or_continental", "global_or_universal", "non_geographic"
    ],
    "information_granularity": [
        "general_overview", "detailed_account", "highly_specific", "definitional", "enumerative"
    ],
    "intertextual_density": [
        "no_references", "sparse", "moderate", "dense", "uncertain"
    ],
    "named_entity_focus": [
        "person_centric", "organization_centric", "place_centric", "event_centric",
        "work_centric", "concept_or_topic_centric", "mixed"
    ],
    "narrative_perspective": [
        "first_person_singular", "first_person_plural", "second_person",
        "third_person_personal", "third_person_impersonal", "mixed_or_shifting"
    ],
    "quantitative_content_density": [
        "no_quantitative", "incidental_numbers", "moderate_quantitative", "data_rich"
    ],
    "reliability_signals": [
        "evidence_based", "source_attributed", "first_hand_account",
        "procedurally_documented", "analytical_inference", "speculative_or_uncertain",
        "asserted_without_support", "promotional_or_advocacy",
        "partisan_or_propagandistic", "fictional_or_imaginative_frame"
    ],
    "structural_form": [
        "continuous_prose", "verse_lines", "list_or_enumeration", "tabular",
        "form_based_record", "ledger_or_account_entry", "header_or_title_block",
        "dialogue_turns", "navigation_or_reference_apparatus", "quoted_block",
        "entry_like_units", "other_structure", "garbage"
    ],
    "style": [
        "formal", "neutral", "informal", "bureaucratic", "scholarly",
        "journalistic", "didactic", "devotional", "literary", "promotional",
        "formulaic"
    ],
    "subject_domain": [
        "ddc_000_generalia", "ddc_100_philosophy_psychology", "ddc_200_religion",
        "ddc_300_social_sciences", "ddc_400_language", "ddc_500_natural_sciences",
        "ddc_600_applied_sciences", "ddc_700_arts_recreation", "ddc_800_literature",
        "ddc_900_history_geography", "news_and_current_affairs",
        "official_and_legal_documents", "personal_and_private_documents",
        "commercial_and_trade_documents"
    ],
    "temporal_reference_frame": [
        "contemporary_to_authorship", "historical_past", "remote_or_mythological_past",
        "future_or_projective", "timeless_or_general", "mixed_temporal", "uncertain"
    ],
    "textual_stance": [
        "neutral_descriptive", "interpretive", "evaluative", "persuasive",
        "normative", "committed_assertive", "hedged_or_cautious",
        "partisan_or_polemical", "satirical_or_ironic"
    ]
}


def get_language_user_form(code: str) -> str:
    return LANGUAGE_MAP.get(code.lower(), code.capitalize())


_MINOR_TITLE_CASE_WORDS = {
    "a", "an", "the", "and", "or", "but", "nor", "to", "of", "in", "on", "for", "at", "by", "with"
}


def _title_case(words: list[str]) -> str:
    return " ".join(
        word.lower() if i > 0 and word.lower() in _MINOR_TITLE_CASE_WORDS else word.capitalize()
        for i, word in enumerate(words)
    )


def _format_user_form(backend_val: str) -> str:
    if backend_val.startswith("ddc_"):
        parts = backend_val.split("_")
        prefix = parts[0].upper()
        code = parts[1]
        rest = _title_case(parts[2:])
        return f"{prefix} {code} {rest}".strip()
    return _title_case(backend_val.split("_"))


async def fetch_db_filter_stats(config_obj=None) -> tuple[int | None, int | None, list[str] | None]:
    """
    Connects to Weaviate and queries minimum and maximum yearIssued and unique languages.
    Returns (min_year, max_year, languages_list).
    """
    if config_obj is None:
        from semant_demo.config import config as default_config
        config_obj = default_config

    try:
        w = await WeaviateAbstraction.create(config_obj)
        min_year = None
        max_year = None
        languages = []

        try:
            doc_col = w.client.collections.get(config_obj.collectionNames.document_collection_name)
            
            # Query year range
            res_year = await doc_col.aggregate.over_all(
                return_metrics=[Metrics("yearIssued").integer(minimum=True, maximum=True)]
            )
            if "yearIssued" in res_year.properties:
                m_min = res_year.properties["yearIssued"].minimum
                m_max = res_year.properties["yearIssued"].maximum
                if m_min is not None:
                    min_year = int(m_min)
                if m_max is not None:
                    max_year = int(m_max)

            # Query languages
            res_lang = await doc_col.aggregate.over_all(
                return_metrics=[Metrics("language").text(top_occurrences_value=True, limit=1000)]
            )
            if "language" in res_lang.properties and res_lang.properties["language"].top_occurrences:
                languages = [
                    top.value for top in res_lang.properties["language"].top_occurrences if top.value
                ]
        finally:
            await w.close()

        return min_year, max_year, languages if languages else None
    except Exception as e:
        logging.warning(f"Could not fetch filter stats from DB: {e}")
        return None, None, None


def generate_default_filters(
    min_year: int | None = None,
    max_year: int | None = None,
    languages: list[str] | None = None,
) -> SearchFiltersResponse:
    filters: list[SearchFilter] = []

    # 1. Year range (interval filter)
    filters.append(
        SearchFilter(
            id="year_range",
            name="Year range",
            type=FilterType.interval,
            description=(
                "It is filter for text chunks stored in Chunks collection, "
                "which are associated with document having yearIssued property value "
                "belonging to the given interval."
            ),
            target_property="yearIssued",
            min_value=min_year,
            max_value=max_year,
        )
    )

    # 2. Language (nominal filter)
    if languages:
        lang_nominal_values = [
            NominalFilterValue(user_form=get_language_user_form(code), backend_form=code)
            for code in languages
        ]
    else:
        default_languages = [
            ("Czech", "cs"),
            ("English", "en"),
            ("German", "de"),
            ("French", "fr"),
            ("Spanish", "es"),
            ("Slovak", "sk"),
            ("Latin", "la"),
        ]
        lang_nominal_values = [
            NominalFilterValue(user_form=user, backend_form=backend)
            for user, backend in default_languages
        ]

    filters.append(
        SearchFilter(
            id="language",
            name="Language",
            type=FilterType.nominal,
            description=(
                "Allows to select only Chunks, having language property value in given set language codes."
            ),
            target_property="language",
            values=lang_nominal_values,
        )
    )

    # 3. TASK_CLASSES nominal filters
    for filter_key, class_values in TASK_CLASSES.items():
        filter_name = filter_key.replace("_", " ").title()
        nominal_values = [
            NominalFilterValue(
                user_form=_format_user_form(val),
                backend_form=val,
            )
            for val in class_values
        ]
        filters.append(
            SearchFilter(
                id=filter_key,
                name=filter_name,
                type=FilterType.nominal,
                description=f"Allows to select only Chunks, having {filter_key} property value in given set.",
                target_property=filter_key,
                values=nominal_values,
            )
        )

    return SearchFiltersResponse(filters=filters)


async def generate_default_filters_async(config_obj=None) -> SearchFiltersResponse:
    min_year, max_year, languages = await fetch_db_filter_stats(config_obj)
    return generate_default_filters(min_year=min_year, max_year=max_year, languages=languages)


def save_search_filters_config(config_path: Union[str, Path], response: SearchFiltersResponse) -> None:
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = response.model_dump(mode="json")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def load_search_filters_config(config_path: Union[str, Path]) -> SearchFiltersResponse:
    path = Path(config_path)
    if not path.exists():
        logging.warning(f"Search filters config not found at {path}, generating default filters")
        defaults = generate_default_filters()
        try:
            save_search_filters_config(path, defaults)
        except Exception:
            pass
        return defaults

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "filters" not in data:
        logging.warning(f"Search filters config at {path} is empty or invalid, generating default filters")
        return generate_default_filters()

    return SearchFiltersResponse.model_validate(data)


class InvalidSearchFilterError(ValueError):
    """Base exception for invalid search filter validation."""
    pass


class InvalidFilterIDError(InvalidSearchFilterError):
    def __init__(self, filter_id: str, valid_ids: list[str]):
        self.filter_id = filter_id
        self.valid_ids = valid_ids
        sorted_ids = ", ".join(sorted(valid_ids))
        super().__init__(
            f"Invalid search filter: filter '{filter_id}' is not supported. Available filters are: {sorted_ids}."
        )


class DuplicateFilterIDError(InvalidSearchFilterError):
    def __init__(self, filter_id: str):
        self.filter_id = filter_id
        super().__init__(f"Invalid search filter: duplicate filter '{filter_id}' specified in request.")


class InvalidFilterValueError(InvalidSearchFilterError):
    def __init__(self, filter_id: str, value: str, valid_values: list[str]):
        self.filter_id = filter_id
        self.value = value
        self.valid_values = valid_values
        sorted_vals = ", ".join(sorted(set(valid_values)))
        super().__init__(
            f"Invalid filter value: '{value}' is not a valid option for filter '{filter_id}'. Valid choices are: {sorted_vals}."
        )


class InvalidFilterRangeError(InvalidSearchFilterError):
    def __init__(self, filter_id: str, reason: str):
        self.filter_id = filter_id
        self.reason = reason
        super().__init__(f"Invalid filter range for '{filter_id}': {reason}.")


DOC_PROPERTIES = {
    "yearIssued", "dateIssued", "documentType", "publisher", "placeTerm",
    "genre", "public", "url", "library", "title", "subTitle", "partNumber",
    "partName", "authors", "description", "keywords", "section", "region", "id_code"
}


def _get_prop_filter(target_property: str):
    from weaviate.classes.query import Filter
    if target_property in DOC_PROPERTIES:
        return Filter.by_ref(link_on="document").by_property(target_property)
    return Filter.by_property(target_property)


from typing import Any


def parse_and_validate_search_filters(
    requested_filters: list[SearchFilterInput] | None,
    available_filters: SearchFiltersResponse
) -> list[Any] | None:
    """
    Parses and validates a list of SearchFilterInput against defined available search filters.
    Raises InvalidSearchFilterError subclass with API-suitable detail message if invalid.

    :return:Returns a list of Weaviate Filter objects or None for indicating legacy call.
    """
    weaviate_filters = []
    defined_filters_map = {f.id: f for f in available_filters.filters}

    if not requested_filters:
        return None

    seen_ids = set()
    for input_filter in requested_filters:
        f_id = input_filter.id
        if f_id not in defined_filters_map:
            raise InvalidFilterIDError(f_id, list(defined_filters_map.keys()))

        if f_id in seen_ids:
            raise DuplicateFilterIDError(f_id)
        seen_ids.add(f_id)

        defined_filter = defined_filters_map[f_id]
        f_type = getattr(defined_filter.type, "value", str(defined_filter.type))
        target_prop = defined_filter.target_property

        if f_type == "interval":
            min_val = input_filter.min_value
            max_val = input_filter.max_value

            if min_val is None and max_val is None:
                raise InvalidFilterRangeError(f_id, "at least one of 'min_value' or 'max_value' must be provided")

            if min_val is not None and max_val is not None and min_val > max_val:
                raise InvalidFilterRangeError(
                    f_id, f"min_value ({min_val}) cannot be greater than max_value ({max_val})"
                )

            if min_val is not None:
                weaviate_filters.append(_get_prop_filter(target_prop).greater_or_equal(min_val))
            if max_val is not None:
                weaviate_filters.append(_get_prop_filter(target_prop).less_or_equal(max_val))

        elif f_type == "nominal":
            raw_values = input_filter.values
            if raw_values is None:
                values_list = []
            elif isinstance(raw_values, (list, tuple, set)):
                values_list = list(raw_values)
            else:
                values_list = [raw_values]

            if not values_list:
                raise InvalidFilterRangeError(f_id, "'values' list cannot be empty")

            mapped_values = []
            if defined_filter.values:
                valid_forms = {}
                allowed_display = []
                for nv in defined_filter.values:
                    valid_forms[nv.backend_form.lower()] = nv.backend_form
                    valid_forms[nv.user_form.lower()] = nv.backend_form
                    allowed_display.append(nv.backend_form)

                for v in values_list:
                    str_v = str(v).lower()
                    if str_v not in valid_forms:
                        raise InvalidFilterValueError(f_id, str(v), allowed_display)
                    mapped_values.append(valid_forms[str_v])
            else:
                mapped_values = [str(v) for v in values_list]

            weaviate_filters.append(_get_prop_filter(target_prop).contains_any(mapped_values))

    return weaviate_filters
