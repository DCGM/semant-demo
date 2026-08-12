# Search Filters Configuration

This document explains how search filters are configured, validated, and applied in the backend of the Semant Demo application.

## Overview
Search filters allow users to restrict text chunk searches based on document metadata properties (e.g., year of issue, language, communicative mode, etc.). 
The filters are driven by a centralized YAML configuration file that defines which filters are available, their types, their human-readable descriptions, and their valid choices.

## 1. The Configuration File
The search filters configuration is stored in:
`semant_demo_backend/semant_demo/configs/search_filters.yaml`

This file is automatically loaded at runtime. It represents a `SearchFiltersResponse` object. Each filter in the YAML contains:
- `id`: A unique internal ID (e.g., `year_range`, `language`, `complexity`).
- `name`: A human-readable display name.
- `type`: Either `interval` (for ranges, like years) or `nominal` (for categorical enums).
- `description`: Instructions/details for the frontend/user.
- `target_property`: The backend Weaviate property name.
- `values`: (For nominal types) A list of valid options, mapped between a `user_form` and `backend_form`.
- `min_value` / `max_value`: (For interval types) The absolute boundaries allowed for the filter.

## 2. Default Configuration Generation
To avoid hardcoding dynamic data like the absolute maximum and minimum document years or available languages, the configuration can be generated programmatically using `create_default_configurations.py`.

Under the hood, `generate_default_filters_async()` (in `search_filters.py`) connects to the Weaviate database and runs aggregations to fetch the `min` and `max` limits for `yearIssued` and the top occurring `language` codes.
The script then writes these dynamically discovered values, along with static classification tasks (like `communicative_mode`, `complexity`), into the `search_filters.yaml` file.

*If the YAML file is deleted or missing during runtime, `load_search_filters_config()` will automatically query the database to regenerate and save the defaults.*

## 3. Exposing Filters via the API
The frontend can request the currently available filters via the GET `/api/search/filters` endpoint (defined in `search_routes.py`). This endpoint simply reads the active configuration and returns the `SearchFiltersResponse` schema. This allows the UI to dynamically render dropdowns, sliders, and checkboxes without hardcoding filter logic on the client.

## 4. Applying Filters in Search
When a user submits a search request to the POST `/api/search` endpoint, they include their desired filters. The pipeline works as follows:

1. **Validation (`parse_and_validate_search_filters`)**:
   Located in `search_filters.py`, this function validates the user's input against the loaded YAML configuration.
   - It checks that the requested filter `id` exists.
   - For `interval` types, it validates that the provided min/max bounds are logical.
   - For `nominal` types, it verifies that the requested value matches one of the allowed `backend_form` or `user_form` choices defined in the configuration.
   - Raises informative `HTTPException` (400 Bad Request) errors if invalid data is passed.

2. **Weaviate Query Construction (`_get_prop_filter`)**:
   During validation, requested filters are mapped to native Weaviate `Filter` objects. Depending on whether the `target_property` belongs to the `Document` collection (e.g., `yearIssued`, `genre`) or the `Chunk` collection itself, it applies the correct reference linkage (`Filter.by_ref(link_on="document")`).

3. **Database Execution (`text_chunk.py`)**:
   The `TextChunk.search()` method takes the combined Weaviate filters and injects them directly into the `.hybrid()`, `.bm25()`, or `.near_vector()` Weaviate queries to safely and efficiently restrict the search results.
