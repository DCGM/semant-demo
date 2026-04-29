import logging
import random
import uuid
from typing import NoReturn

import httpx
from fastapi import APIRouter, HTTPException, status

from semant_demo import schemas
from semant_demo.config import config


exp_router = APIRouter()
LOGGER = logging.getLogger(__name__)

TOPICER_DISCOVER_TOPICS_DENSE_PATH = "/v1/topics/discover/texts/dense"
TOPICER_DISCOVER_TOPICS_SPARSE_PATH = "/v1/topics/discover/texts/sparse"
TOPICER_PROPOSE_TAGS_TEXTS_PATH = "/v1/tags/propose/texts"
TOPICER_CONFIGS_PATH = "/v1/configs"


def _fallback_tag_id(tag: schemas.TagData) -> str:
    """Use provided tag UUID when available, otherwise create fallback ID."""
    if tag.tag_uuid is not None:
        return str(tag.tag_uuid)

    base = f"{tag.collection_name}:{tag.tag_name}:{tag.tag_shorthand}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


def _build_suggestions(
    payload: schemas.AutoAnnotationSuggestionRequest,
) -> list[schemas.AutoAnnotationSuggestion]:
    suggestions: list[schemas.AutoAnnotationSuggestion] = []

    for chunk in payload.chunks:
        for tag in payload.tags:
            tag_id = _fallback_tag_id(tag)
            text_len = len(chunk.text)

            if text_len == 0:
                start = 0
                end = 0
            else:
                start = random.randint(0, text_len - 1)
                end = random.randint(start + 1, text_len)

            suggestion_id = str(uuid.uuid4())

            suggestions.append(
                schemas.AutoAnnotationSuggestion(
                    id=suggestion_id,
                    chunkId=str(chunk.id),
                    tagId=tag_id,
                    start=start,
                    end=end,
                    type=schemas.SpanType.auto,
                    confidence=random.random(),
                )
            )
    return suggestions


def _build_topicer_chunk_payload(
    chunks: list[schemas.TextChunk],
) -> list[dict[str, str]]:
    return [{"id": str(chunk.id), "text": chunk.text} for chunk in chunks]


def _build_topicer_tags_payload(
    tags: list[schemas.TagData],
) -> list[dict[str, str]]:
    return [
        {
            "id": _fallback_tag_id(tag),
            "name": tag.tag_name,
            "description": tag.tag_definition,
        }
        for tag in tags
    ]


def _topicer_proposal_to_auto_suggestions(
    payload: object,
    fallback_chunk_id: str,
) -> list[schemas.AutoAnnotationSuggestion]:
    if not isinstance(payload, dict):
        raise ValueError("Topicer propose tags payload must be an object.")

    chunk_id = payload.get("id")
    if not isinstance(chunk_id, str) or chunk_id == "":
        chunk_id = fallback_chunk_id

    proposals = payload.get("tag_span_proposals")
    if not isinstance(proposals, list):
        raise ValueError("Topicer propose tags payload is missing 'tag_span_proposals'.")

    suggestions: list[schemas.AutoAnnotationSuggestion] = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ValueError("Topicer tag span proposal must be an object.")

        tag = proposal.get("tag")
        if not isinstance(tag, dict):
            raise ValueError("Topicer tag span proposal is missing 'tag'.")

        tag_id = tag.get("id")
        if not isinstance(tag_id, str) or tag_id == "":
            raise ValueError("Topicer tag span proposal tag is missing valid 'id'.")

        span_start = proposal.get("span_start")
        span_end = proposal.get("span_end")
        if not isinstance(span_start, int) or not isinstance(span_end, int):
            raise ValueError("Topicer tag span proposal has invalid span boundaries.")

        confidence = proposal.get("confidence")
        confidence_value = float(confidence) if confidence is not None else 0.0

        suggestions.append(
            schemas.AutoAnnotationSuggestion(
                id=str(uuid.uuid4()),
                chunkId=chunk_id,
                tagId=tag_id,
                start=span_start,
                end=span_end,
                type=schemas.SpanType.auto,
                confidence=confidence_value,
            )
        )

    return suggestions


def _select_confident_suggestions(
    suggestions: list[schemas.AutoAnnotationSuggestion],
    confidence_threshold: float,
    max_count: int = 3,
) -> list[schemas.AutoAnnotationSuggestion]:
    confident = [
        suggestion
        for suggestion in suggestions
        if suggestion.confidence >= confidence_threshold
    ]
    confident.sort(key=lambda suggestion: suggestion.confidence, reverse=True)
    return confident[:max_count]


def _raise_topicer_gateway_error(detail: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
    )


async def _resolve_topicer_config_candidates(client: httpx.AsyncClient) -> list[str]:
    if config.TOPICER_CONFIG_NAME:
        return [config.TOPICER_CONFIG_NAME]

    response = await client.get(
        f"{config.TOPICER_URL}{TOPICER_CONFIGS_PATH}",
        timeout=config.TOPICER_TIMEOUT,
    )
    response.raise_for_status()

    names = response.json()
    if not isinstance(names, list) or len(names) == 0:
        raise ValueError("Topicer returned no available configs.")

    valid_names = [name for name in names if isinstance(name, str) and name != ""]
    if len(valid_names) == 0:
        raise ValueError("Topicer returned invalid config list.")

    return valid_names


def _extract_topicer_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()

    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail

    return str(payload)


def _is_method_not_applicable_error(response: httpx.Response) -> bool:
    return "method not applicable" in _extract_topicer_error_detail(response).lower()


def _sparse_topic_documents_to_dense(
    sparse_topic_documents: list[list[tuple[int, float]]],
    chunk_count: int,
) -> list[list[float]]:
    dense_topic_documents = [
        [0.0 for _ in range(chunk_count)]
        for _ in range(len(sparse_topic_documents))
    ]

    for topic_index, topic_documents in enumerate(sparse_topic_documents):
        for chunk_index, probability in topic_documents:
            if 0 <= chunk_index < chunk_count:
                dense_topic_documents[topic_index][chunk_index] = probability

    return dense_topic_documents


@exp_router.post(
    "/api/propose_tags_mock",
    response_model=schemas.AutoAnnotationsSuggestionsResponse,
)
async def propose_tags_mock(
    body: schemas.AutoAnnotationSuggestionRequest,
) -> schemas.AutoAnnotationsSuggestionsResponse:
    """Mock of Topicer propose_tags that returns random auto suggestions."""
    return schemas.AutoAnnotationsSuggestionsResponse(
        suggestions=_build_suggestions(body)
    )


@exp_router.post(
    "/api/propose_tags",
    response_model=schemas.AutoAnnotationsSuggestionsResponse,
)
async def propose_tags(
    body: schemas.AutoAnnotationSuggestionRequest,
) -> schemas.AutoAnnotationsSuggestionsResponse:
    """Call Topicer tag proposal on provided chunks and tags."""
    if len(body.chunks) == 0 or len(body.tags) == 0:
        return schemas.AutoAnnotationsSuggestionsResponse(suggestions=[])

    topicer_tags = _build_topicer_tags_payload(body.tags)

    try:
        async with httpx.AsyncClient() as client:
            config_candidates = ['ollama']
            method_not_applicable_configs: list[str] = []

            for config_name in config_candidates:
                all_suggestions: list[schemas.AutoAnnotationSuggestion] = []

                for chunk in body.chunks:
                    response = await client.post(
                        f"{config.TOPICER_URL}{TOPICER_PROPOSE_TAGS_TEXTS_PATH}",
                        params={"config_name": config_name},
                        json={
                            "text_chunk": {
                                "id": str(chunk.id),
                                "text": chunk.text,
                            },
                            "tags": topicer_tags,
                        },
                        timeout=config.TOPICER_TIMEOUT,
                    )

                    if response.status_code >= 400:
                        if _is_method_not_applicable_error(response):
                            method_not_applicable_configs.append(config_name)
                            break
                        response.raise_for_status()

                    try:
                        chunk_suggestions = _topicer_proposal_to_auto_suggestions(
                            response.json(),
                            fallback_chunk_id=str(chunk.id),
                        )
                    except Exception as exc:
                        LOGGER.exception("Topicer returned invalid propose tags payload.")
                        _raise_topicer_gateway_error(f"Topicer returned invalid propose tags payload: {exc}")

                    all_suggestions.extend(chunk_suggestions)
                else:
                    return schemas.AutoAnnotationsSuggestionsResponse(suggestions=all_suggestions)

            if len(method_not_applicable_configs) > 0:
                unique_configs = sorted(set(method_not_applicable_configs))
                joined_configs = ", ".join(unique_configs)
                _raise_topicer_gateway_error(
                    "Tag proposal is not implemented for available Topicer configs: "
                    f"{joined_configs}. Set TOPICER_CONFIG_NAME to a config that supports tag proposal."
                )
    except httpx.HTTPStatusError as exc:
        response_text = _extract_topicer_error_detail(exc.response)[:500]
        LOGGER.exception("Topicer returned an error response.")
        _raise_topicer_gateway_error(
            f"Topicer request failed with status {exc.response.status_code}: {response_text}"
        )
    except httpx.HTTPError as exc:
        LOGGER.exception("Topicer request failed.")
        _raise_topicer_gateway_error(f"Unable to contact Topicer: {exc}")
    except ValueError as exc:
        LOGGER.exception("Topicer configuration resolution failed.")
        _raise_topicer_gateway_error(str(exc))

    _raise_topicer_gateway_error("Topicer request did not produce a valid response.")


@exp_router.post(
    "/api/propose_best_tag",
    response_model=schemas.BestTagProposalResponse,
)
async def propose_best_tag(
    body: schemas.BestTagProposalRequest,
) -> schemas.BestTagProposalResponse:
    """Call Topicer tag proposal and return top confident tags."""
    if body.text.strip() == "" or len(body.tags) == 0:
        return schemas.BestTagProposalResponse(suggestions=[])

    fallback_chunk_id = str(uuid.uuid4())
    topicer_tags = _build_topicer_tags_payload(body.tags)
    tag_by_id = {
        _fallback_tag_id(tag): tag
        for tag in body.tags
    }

    try:
        async with httpx.AsyncClient() as client:
            config_candidates = ["ollama"]
            method_not_applicable_configs: list[str] = []

            for config_name in config_candidates:
                response = await client.post(
                    f"{config.TOPICER_URL}{TOPICER_PROPOSE_TAGS_TEXTS_PATH}",
                    params={"config_name": config_name},
                    json={
                        "text_chunk": {
                            "id": fallback_chunk_id,
                            "text": body.text,
                        },
                        "tags": topicer_tags,
                    },
                    timeout=config.TOPICER_TIMEOUT,
                )

                if response.status_code >= 400:
                    if _is_method_not_applicable_error(response):
                        method_not_applicable_configs.append(config_name)
                        continue
                    response.raise_for_status()

                try:
                    suggestions = _topicer_proposal_to_auto_suggestions(
                        response.json(),
                        fallback_chunk_id=fallback_chunk_id,
                    )
                except Exception as exc:
                    LOGGER.exception("Topicer returned invalid propose tags payload.")
                    _raise_topicer_gateway_error(
                        f"Topicer returned invalid propose tags payload: {exc}"
                    )

                top_suggestions = _select_confident_suggestions(
                    suggestions=suggestions,
                    confidence_threshold=body.confidence_threshold,
                    max_count=3,
                )

                return schemas.BestTagProposalResponse(
                    suggestions=[
                        schemas.BestTagProposal(
                            tagId=suggestion.tagId,
                            confidence=suggestion.confidence,
                            start=suggestion.start,
                            end=suggestion.end,
                            tag=tag_by_id.get(suggestion.tagId),
                        )
                        for suggestion in top_suggestions
                    ]
                )

            if len(method_not_applicable_configs) > 0:
                unique_configs = sorted(set(method_not_applicable_configs))
                joined_configs = ", ".join(unique_configs)
                _raise_topicer_gateway_error(
                    "Tag proposal is not implemented for available Topicer configs: "
                    f"{joined_configs}. Set TOPICER_CONFIG_NAME to a config that supports tag proposal."
                )
    except httpx.HTTPStatusError as exc:
        response_text = _extract_topicer_error_detail(exc.response)[:500]
        LOGGER.exception("Topicer returned an error response.")
        _raise_topicer_gateway_error(
            f"Topicer request failed with status {exc.response.status_code}: {response_text}"
        )
    except httpx.HTTPError as exc:
        LOGGER.exception("Topicer request failed.")
        _raise_topicer_gateway_error(f"Unable to contact Topicer: {exc}")
    except ValueError as exc:
        LOGGER.exception("Topicer configuration resolution failed.")
        _raise_topicer_gateway_error(str(exc))

    _raise_topicer_gateway_error("Topicer request did not produce a valid response.")


@exp_router.post(
    "/api/discover_topics",
    response_model=schemas.DiscoveredTopics,
)
async def discover_topics(
    body: schemas.DiscoverTopicsRequest,
) -> schemas.DiscoveredTopics:
    """Call Topicer dense topic discovery on the provided chunks."""
    if len(body.chunks) == 0:
        return schemas.DiscoveredTopics(topics=[], topic_documents=[])

    topicer_chunks = _build_topicer_chunk_payload(body.chunks)

    try:
        async with httpx.AsyncClient() as client:
            config_candidates = await _resolve_topicer_config_candidates(client)
            method_not_applicable_configs: list[str] = []

            for config_name in config_candidates:
                params: dict[str, str | int] = {"config_name": config_name}
                if body.n is not None:
                    params["n"] = body.n

                dense_response = await client.post(
                    f"{config.TOPICER_URL}{TOPICER_DISCOVER_TOPICS_DENSE_PATH}",
                    params=params,
                    json=topicer_chunks,
                    timeout=config.TOPICER_TIMEOUT,
                )

                if dense_response.status_code < 400:
                    try:
                        return schemas.DiscoveredTopics(**dense_response.json())
                    except Exception as exc:
                        LOGGER.exception("Topicer returned invalid dense discover topics payload.")
                        _raise_topicer_gateway_error(f"Topicer returned invalid dense payload: {exc}")

                if _is_method_not_applicable_error(dense_response):
                    sparse_response = await client.post(
                        f"{config.TOPICER_URL}{TOPICER_DISCOVER_TOPICS_SPARSE_PATH}",
                        params=params,
                        json=topicer_chunks,
                        timeout=config.TOPICER_TIMEOUT,
                    )

                    if sparse_response.status_code < 400:
                        try:
                            sparse_topics = schemas.DiscoveredTopicsSparse(**sparse_response.json())
                        except Exception as exc:
                            LOGGER.exception("Topicer returned invalid sparse discover topics payload.")
                            _raise_topicer_gateway_error(f"Topicer returned invalid sparse payload: {exc}")

                        return schemas.DiscoveredTopics(
                            topics=sparse_topics.topics,
                            topic_documents=_sparse_topic_documents_to_dense(
                                sparse_topics.topic_documents,
                                chunk_count=len(body.chunks),
                            ),
                        )

                    if _is_method_not_applicable_error(sparse_response):
                        method_not_applicable_configs.append(config_name)
                        continue

                    sparse_response.raise_for_status()

                dense_response.raise_for_status()

            if len(method_not_applicable_configs) > 0:
                joined_configs = ", ".join(method_not_applicable_configs)
                _raise_topicer_gateway_error(
                    "Topic discovery is not implemented for available Topicer configs: "
                    f"{joined_configs}. Set TOPICER_CONFIG_NAME to a config that supports topic discovery."
                )
    except httpx.HTTPStatusError as exc:
        response_text = _extract_topicer_error_detail(exc.response)[:500]
        LOGGER.exception("Topicer returned an error response.")
        _raise_topicer_gateway_error(
            f"Topicer request failed with status {exc.response.status_code}: {response_text}"
        )
    except httpx.HTTPError as exc:
        LOGGER.exception("Topicer request failed.")
        _raise_topicer_gateway_error(f"Unable to contact Topicer: {exc}")
    except ValueError as exc:
        LOGGER.exception("Topicer configuration resolution failed.")
        _raise_topicer_gateway_error(str(exc))

    _raise_topicer_gateway_error("Topicer request did not produce a valid response.")
