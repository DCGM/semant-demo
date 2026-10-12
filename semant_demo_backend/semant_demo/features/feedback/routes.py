"""Application feedback HTTP route; delivery lives in ``service.py``."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from semant_demo.config import Config
from semant_demo.features.feedback import service
from semant_demo.features.feedback.schemas import AppFeedbackRequest
from semant_demo.routes.dependencies import get_config

logger = logging.getLogger(__name__)

exp_router = APIRouter()


@exp_router.post('/api/v1/feedback')
async def save_app_feedback(payload: AppFeedbackRequest, req: Request,
                            config: Config = Depends(get_config)):
    service.check_message(payload)
    try:
        service.deliver(config, payload, source_ip=req.client.host if req.client else None,
                        user_agent=req.headers.get('user-agent'))
    except Exception as err:
        # Content-free: the error may quote the webhook URL, which can hold a token.
        logger.error('App feedback delivery error: %s', type(err).__name__)
        raise HTTPException(status_code=500, detail='Failed to deliver feedback.')
    return {'status': 'success'}
