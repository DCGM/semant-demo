import random
import uuid

from fastapi import APIRouter

from semant_demo import schemas


exp_router = APIRouter()


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


@exp_router.post(
    "/api/propose_tags",
    response_model=schemas.AutoAnnotationsSuggestionsResponse,
)
async def propose_tags(
    body: schemas.AutoAnnotationSuggestionRequest,
) -> schemas.AutoAnnotationsSuggestionsResponse:
    """Mock of Topicer propose_tags that returns random auto suggestions."""
    return schemas.AutoAnnotationsSuggestionsResponse(
        suggestions=_build_suggestions(body)
    )
