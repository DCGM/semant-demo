"""
Client for the tagging worker.

Usage
-----
    from tagging_client import TaggingClient
    from schemas import TaggingTaskReqTemplate, TaggingConfig, TaggingConfigParams, APIType

    client = TaggingClient()

    task_req = TaggingTaskReqTemplate(
        tag_name="Named entity – person",
        tag_shorthand="PER",
        tag_color="#e63946",
        tag_pictogram="person",
        tag_definition="Text mentions a real or fictional person by name.",
        tag_examples=["Jan Novák přijel do Prahy.", "Marie Curie discovered radium."],
        collection_name="my_collection",
        task_config=TaggingConfig(
            name="ollama-default",
            description="Local Ollama run",
            class_name="OllamaTagging",
            params=TaggingConfigParams(
                model_type=APIType.ollama,
                model_name="gemma3:4b",
                temperature=0.0,
            ),
        ),
    )

    task_id = client.submit(task_req)
    result  = client.wait(task_id, timeout=300)
    print(result)
"""

from __future__ import annotations

import logging
import time
from typing import Any

from celery import Celery
from celery.result import AsyncResult

from schemas import TaggingTaskReqTemplate

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class TaggingClient:
    """
    Thin wrapper around the Celery app that lets you submit tagging tasks
    and poll their status without importing any worker internals.

    Parameters
    ----------
    redis_host:
        Hostname of the Redis broker/backend (default ``"localhost"``).
    redis_port:
        Redis port (default ``6379``).
    """

    #: Name that the worker registers the tagging task under.
    TASK_NAME = "tasks.tagging.run_tagging_task"

    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379) -> None:
        broker = f"redis://{redis_host}:{redis_port}/0"
        backend = f"redis://{redis_host}:{redis_port}/0"

        self._app = Celery("tagging_client", broker=broker, backend=backend)
        self._app.config_from_object(
            {
                "task_serializer": "json",
                "result_serializer": "json",
                "accept_content": ["json"],
                "timezone": "Europe/Prague",
                "enable_utc": True,
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, task_req: TaggingTaskReqTemplate) -> str:
        """
        Send a tagging task to the worker queue.

        Parameters
        ----------
        task_req:
            Fully populated :class:`TaggingTaskReqTemplate` instance.

        Returns
        -------
        str
            Celery task ID that can be passed to :meth:`status` or :meth:`wait`.
        """
        payload = task_req.model_dump()
        result: AsyncResult = self._app.send_task(self.TASK_NAME, kwargs={"task_req": payload})
        logger.info("Submitted tagging task %s (tag=%s)", result.id, task_req.tag_name)
        return result.id

    def status(self, task_id: str) -> dict[str, Any]:
        """
        Return the current status of a task.

        Returns
        -------
        dict with keys:
            ``task_id``, ``state``, ``result`` (when finished),
            ``error`` (when failed), ``traceback`` (when failed).
        """
        ar = AsyncResult(task_id, app=self._app)
        info: dict[str, Any] = {"task_id": task_id, "state": ar.state}

        if ar.state == "SUCCESS":
            info["result"] = ar.result
        elif ar.state == "FAILURE":
            info["error"] = str(ar.result)
            info["traceback"] = ar.traceback
        elif ar.state == "PROGRESS":
            # worker may push custom progress metadata
            info["meta"] = ar.info

        return info

    def wait(
        self,
        task_id: str,
        *,
        timeout: float = 600.0,
        poll_interval: float = 2.0,
    ) -> dict[str, Any]:
        """
        Block until *task_id* finishes or *timeout* seconds have elapsed.

        Parameters
        ----------
        task_id:
            ID returned by :meth:`submit`.
        timeout:
            Maximum seconds to wait (default 600).
        poll_interval:
            Seconds between status polls (default 2).

        Returns
        -------
        dict
            Same shape as :meth:`status`.

        Raises
        ------
        TimeoutError
            If the task has not finished within *timeout* seconds.
        RuntimeError
            If the task finished with state FAILURE.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            info = self.status(task_id)
            state = info["state"]

            if state == "SUCCESS":
                logger.info("Task %s completed successfully.", task_id)
                return info

            if state == "FAILURE":
                raise RuntimeError(
                    f"Task {task_id} failed: {info.get('error')}\n{info.get('traceback', '')}"
                )

            logger.debug("Task %s state=%s – waiting …", task_id, state)
            time.sleep(poll_interval)

        raise TimeoutError(f"Task {task_id} did not finish within {timeout}s.")

    def revoke(self, task_id: str, *, terminate: bool = False) -> None:
        """
        Cancel a pending or running task.

        Parameters
        ----------
        terminate:
            If ``True`` the worker process executing the task is sent SIGTERM
            (use with care on shared workers).
        """
        self._app.control.revoke(task_id, terminate=terminate)
        logger.info("Revoked task %s (terminate=%s).", task_id, terminate)
