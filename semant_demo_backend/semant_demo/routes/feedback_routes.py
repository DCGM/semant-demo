import datetime
import json
import logging
from pathlib import Path
from urllib import request as urllib_request

from fastapi import APIRouter, HTTPException, Request

from semant_demo import schemas
from semant_demo.config import config

exp_router = APIRouter()


def _append_feedback_to_log(payload: dict) -> None:
    log_path = Path(config.FEEDBACK_LOG_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as log_file:
        log_file.write(json.dumps(payload, ensure_ascii=False) + '\n')


def _send_feedback_webhook(payload: dict) -> None:
    if not config.FEEDBACK_WEBHOOK_URL:
        return

    req = urllib_request.Request(
        config.FEEDBACK_WEBHOOK_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    with urllib_request.urlopen(req, timeout=5):
        pass


@exp_router.post('/api/feedback')
async def save_app_feedback(payload: schemas.AppFeedbackRequest, req: Request):
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail='Message cannot be empty.')

    feedback_payload = {
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'feedback_type': payload.type,
        'subject': payload.subject,
        'message': payload.message.strip(),
        'email': payload.email,
        'source_ip': req.client.host if req.client else None,
        'user_agent': req.headers.get('user-agent')
    }

    try:
        _append_feedback_to_log(feedback_payload)
        _send_feedback_webhook(feedback_payload)
        return {'status': 'success'}
    except Exception as err:
        logging.error(f'App feedback delivery error: {err}')
        raise HTTPException(status_code=500, detail='Failed to deliver feedback.')
