"""Application feedback: appended to the feedback log and sent to the optional webhook."""
import datetime
import json
from pathlib import Path
from urllib import request as urllib_request

from semant_demo.config import Config
from semant_demo.core.errors import InvalidRequestError
from semant_demo.features.feedback.schemas import AppFeedbackRequest


def _append_feedback_to_log(config: Config, payload: dict) -> None:
    log_path = Path(config.FEEDBACK_LOG_PATH)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as log_file:
        log_file.write(json.dumps(payload, ensure_ascii=False) + '\n')


def _send_feedback_webhook(config: Config, payload: dict) -> None:
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


def check_message(feedback: AppFeedbackRequest) -> None:
    """Raises ``InvalidRequestError`` for an empty message."""
    if not feedback.message or not feedback.message.strip():
        raise InvalidRequestError('Message cannot be empty.')


def deliver(config: Config, feedback: AppFeedbackRequest, source_ip: str | None, user_agent: str | None) -> None:
    """Log the feedback, then send it to the webhook; raises when either fails."""
    payload = {
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'feedback_type': feedback.type,
        'subject': feedback.subject,
        'message': feedback.message.strip(),
        'email': feedback.email,
        'source_ip': source_ip,
        'user_agent': user_agent,
    }
    _append_feedback_to_log(config, payload)
    _send_feedback_webhook(config, payload)
