import io
import json
import logging
from typing import Any, Final

from openai import AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger: Final = logging.getLogger(__name__)


class BatchNotReady(Exception):
    """Raised when batch is still processing."""


class BatchFailedError(Exception):
    """Raised when batch enters a terminal failure state."""


# Models known to not support the batch API
KNOWN_UNSUPPORTED: Final[frozenset[str]] = frozenset(
    {"gpt-realtime-mini", "gpt-4-realtime", "gpt-4o-realtime"}
)


_STAGE_FIELDS: Final[tuple[str, ...]] = (
    "created_at",
    "in_progress_at",
    "finalizing_at",
    "completed_at",
    "failed_at",
    "expired_at",
    "cancelling_at",
    "cancelled_at",
)


class OpenAIBatchClient:
    """Wraps OpenAI SDK for batch-specific operations."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._seen_stages: dict[str, set[str]] = {}

    async def submit_batch(
        self, endpoint: str, request_body: dict[str, object], custom_id: str
    ) -> str:
        """Submit a single-request batch. Returns batch ID."""
        batch_request: dict[str, Any] = {
            "custom_id": custom_id,
            "method": "POST",
            "url": endpoint,
            "body": request_body,
        }
        jsonl_content = json.dumps(batch_request) + "\n"

        file = await self._client.files.create(
            file=("batch_input.jsonl", io.BytesIO(jsonl_content.encode())),
            purpose="batch",
        )
        logger.debug("Uploaded batch input file_id=%s", file.id)

        batch = await self._client.batches.create(
            input_file_id=file.id,
            endpoint=endpoint,  # type: ignore[arg-type]
            completion_window="24h",
        )
        logger.debug("Created batch id=%s input_file=%s endpoint=%s",
                      batch.id, file.id, endpoint)
        return batch.id

    def _log_new_stages(self, batch_id: str, batch: object) -> None:
        """Emit a debug log for each newly populated _at timestamp."""
        seen = self._seen_stages.setdefault(batch_id, set())
        for field in _STAGE_FIELDS:
            ts = getattr(batch, field, None)
            if ts is not None and field not in seen:
                seen.add(field)
                logger.debug("Batch %s stage %s = %s", batch_id, field, ts)

    @retry(
        stop=stop_after_attempt(2880),  # 30s * 2880 = 24h max
        wait=wait_fixed(30),
        retry=retry_if_exception_type(BatchNotReady),
    )
    async def poll_batch(self, batch_id: str) -> dict[str, object]:
        """Poll until batch completes. Raises BatchNotReady to trigger retry."""
        batch = await self._client.batches.retrieve(batch_id)
        self._log_new_stages(batch_id, batch)
        if batch.status == "completed":
            self._seen_stages.pop(batch_id, None)
            if batch.output_file_id is None:
                raise BatchFailedError(f"Batch {batch_id} completed but no output file")
            return await self._download_result(batch.output_file_id)
        if batch.status in ("failed", "expired", "cancelled"):
            self._seen_stages.pop(batch_id, None)
            raise BatchFailedError(f"Batch {batch_id} status: {batch.status}")
        raise BatchNotReady(f"Batch {batch_id} status: {batch.status}")

    async def cancel_batch(self, batch_id: str) -> str:
        """Cancel a batch. Returns final status which may be 'completed' if already done."""
        batch = await self._client.batches.cancel(batch_id)
        return batch.status

    async def sync_call(self, request_body: dict[str, object]) -> dict[str, object]:
        """Direct synchronous API call as fallback."""
        response = await self._client.chat.completions.create(**request_body)  # type: ignore[call-overload]
        return dict(response.model_dump())

    async def check_model_supports_batch(self, model: str) -> bool:
        """Check if a model supports the batch API."""
        return model not in KNOWN_UNSUPPORTED

    async def _download_result(self, output_file_id: str) -> dict[str, object]:
        """Download and parse batch output file."""
        content = await self._client.files.content(output_file_id)
        lines = content.text.strip().split("\n")
        result: dict[str, Any] = json.loads(lines[0])
        body: dict[str, object] = result["response"]["body"]
        return body
