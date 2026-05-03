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

TOPICER_PROPOSE_TAGS_TEXTS_PATH = "/v1/tags/propose/texts"
TOPICER_CONFIGS_PATH = "/v1/configs"
TOPICER_PROPOSE_MOST_PROBABLE_TAG_PATH = "/v1/tags/propose/texts/most_probable"


def _topicer_http_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        connect=config.TOPICER_TIMEOUT,
        read=config.TOPICER_READ_WRITE_TIMEOUT,
        write=config.TOPICER_READ_WRITE_TIMEOUT,
        pool=config.TOPICER_TIMEOUT,
    )


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


class AutoAnnotationSuggestionWithReason(schemas.AutoAnnotationSuggestion):
    reason: str | None = None


def _topicer_proposal_to_auto_suggestions(
    payload: object,
    fallback_chunk_id: str,
) -> list[AutoAnnotationSuggestionWithReason]:
    if not isinstance(payload, dict):
        raise ValueError("Topicer propose tags payload must be an object.")

    chunk_id = payload.get("id")
    if not isinstance(chunk_id, str) or chunk_id == "":
        chunk_id = fallback_chunk_id

    proposals = payload.get("tag_span_proposals")
    if not isinstance(proposals, list):
        raise ValueError(
            "Topicer propose tags payload is missing 'tag_span_proposals'.")

    suggestions: list[AutoAnnotationSuggestionWithReason] = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            raise ValueError("Topicer tag span proposal must be an object.")

        tag = proposal.get("tag")
        if not isinstance(tag, dict):
            raise ValueError("Topicer tag span proposal is missing 'tag'.")

        tag_id = tag.get("id")
        if not isinstance(tag_id, str) or tag_id == "":
            raise ValueError(
                "Topicer tag span proposal tag is missing valid 'id'.")

        span_start = proposal.get("span_start")
        span_end = proposal.get("span_end")
        if not isinstance(span_start, int) or not isinstance(span_end, int):
            raise ValueError(
                "Topicer tag span proposal has invalid span boundaries.")

        confidence = proposal.get("confidence")
        confidence_value = float(confidence) if confidence is not None else 0.0

        reason = proposal.get("reason")

        suggestions.append(
            AutoAnnotationSuggestionWithReason(
                id=str(uuid.uuid4()),
                chunkId=chunk_id,
                tagId=tag_id,
                start=span_start,
                end=span_end,
                type=schemas.SpanType.auto,
                confidence=confidence_value,
                reason=reason,
            )
        )

    return suggestions


def _raise_topicer_gateway_error(detail: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail,
    )


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
            config_name = "openai_gpt"
            method_not_applicable_configs: list[str] = []

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
                    timeout=_topicer_http_timeout(),
                )

                print({
                    "text_chunk": {
                        "id": str(chunk.id),
                        "text": chunk.text,
                    },
                    "tags": topicer_tags,
                },)

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
                    LOGGER.exception(
                        "Topicer returned invalid propose tags payload.")
                    _raise_topicer_gateway_error(
                        f"Topicer returned invalid propose tags payload: {exc}")

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
    except httpx.ReadTimeout as exc:
        LOGGER.exception("Topicer request timed out.")
        _raise_topicer_gateway_error(
            "Topicer request timed out while waiting for LLM response. "
            "Increase TOPICER_READ_WRITE_TIMEOUT (or TOPICER_TIMEOUT)."
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

    _raise_topicer_gateway_error(
        "Topicer request did not produce a valid response.")


@exp_router.post(
    "/api/propose_best_tag",
    response_model=schemas.BestTagProposalResponse,
)
async def propose_best_tag(
    body: schemas.BestTagProposalRequest,
) -> schemas.BestTagProposalResponse:
    """Call Topicer BERT zero-shot tag proposal and return the single most confident tag."""
    if body.text.strip() == "" or len(body.tags) == 0:
        return schemas.BestTagProposalResponse(suggestions=[])

    fallback_chunk_id = str(uuid.uuid4())
    topicer_tags = _build_topicer_tags_payload(body.tags)

    # Rychlý lookup slovník pro namapování zpět na původní tag
    tag_by_id = {
        _fallback_tag_id(tag): tag
        for tag in body.tags
    }

    try:
        async with httpx.AsyncClient() as client:
            # Zde musí být název configu, pod kterým jsi Topicer API spustil
            # (např. název yaml souboru bez přípony). Zůstávám u tvého openai_gpt.
            config_candidates = ["openai_gpt"]
            method_not_applicable_configs: list[str] = []

            for config_name in config_candidates:
                response = await client.post(
                    # VOLÁME NOVÝ ENDPOINT
                    f"{config.TOPICER_URL}{TOPICER_PROPOSE_MOST_PROBABLE_TAG_PATH}",
                    params={"config_name": config_name},
                    json={
                        "text_chunk": {
                            "id": fallback_chunk_id,
                            "text": body.text,
                        },
                        "tags": topicer_tags,
                    },
                    timeout=_topicer_http_timeout(),
                )

                if response.status_code >= 400:
                    if _is_method_not_applicable_error(response):
                        method_not_applicable_configs.append(config_name)
                        continue
                    response.raise_for_status()

                try:
                    # Nový endpoint vrací rovnou {"tag": {...}, "confidence": 0.95} nebo null
                    payload = response.json()
                except Exception as exc:
                    LOGGER.exception("Topicer returned invalid JSON payload.")
                    _raise_topicer_gateway_error(
                        f"Topicer returned invalid JSON: {exc}")

                # Pokud model nenašel vůbec nic (vrátil None/null)
                if not payload:
                    return schemas.BestTagProposalResponse(suggestions=[])

                # Extrakce dat z nového formátu
                topicer_tag = payload.get("tag", {})
                tag_id = topicer_tag.get("id")
                confidence = payload.get("confidence", 0.0)

                if not tag_id:
                    _raise_topicer_gateway_error(
                        "Topicer response missing tag ID.")

                # Filtrování podle threshold hodnoty z requestu
                if confidence < body.confidence_threshold:
                    return schemas.BestTagProposalResponse(suggestions=[])

                # Sestavení odpovědi. BERT zero-shot klasifikuje text jako celek,
                # proto je span od 0 do konce textu.
                proposal = schemas.BestTagProposal(
                    tagId=tag_id,
                    confidence=confidence,
                    start=0,
                    end=len(body.text),
                    tag=tag_by_id.get(tag_id),
                    # reason=f"Klasifikováno modelem BERT s jistotou {confidence:.2f}"
                    reason=f"Classification with confidence of {confidence * 100:.1f}%"
                )

                return schemas.BestTagProposalResponse(
                    suggestions=[proposal]
                )

            # Pokud smyčka doběhne a žádný config neměl metodu implementovanou
            if len(method_not_applicable_configs) > 0:
                unique_configs = sorted(set(method_not_applicable_configs))
                joined_configs = ", ".join(unique_configs)
                _raise_topicer_gateway_error(
                    "Method 'find_most_probable_tag' is not implemented for available configs: "
                    f"{joined_configs}."
                )

    except httpx.ReadTimeout as exc:
        LOGGER.exception("Topicer request timed out.")
        _raise_topicer_gateway_error(
            "Topicer request timed out while waiting for BERT response. "
            "Increase TOPICER_READ_WRITE_TIMEOUT (or TOPICER_TIMEOUT)."
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

    _raise_topicer_gateway_error(
        "Topicer request did not produce a valid response.")
