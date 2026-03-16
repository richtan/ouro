"""Fire-and-forget webhook delivery with retries.

Security model follows industry best practices (GitHub/Stripe/Slack):
- HMAC-SHA256 signature with timestamp to prevent replay attacks
- Unique delivery ID for receiver idempotency
- No redirect following (SSRF prevention)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import asyncio
import uuid
from datetime import datetime, timezone

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
RETRY_DELAYS = [5, 25]  # seconds
TIMEOUT_SECONDS = 10
USER_AGENT = "Ouro-Webhook/1.0"


def _sign_payload(timestamp: str, body: bytes) -> str | None:
    """HMAC-SHA256 signature over timestamp.body, or None if no secret configured.

    Includes timestamp to prevent replay attacks (Stripe/Slack pattern).
    Receivers should reject if timestamp is > 5 minutes old.
    """
    if not settings.WEBHOOK_SECRET:
        return None
    signed_content = f"{timestamp}.".encode() + body
    return hmac.new(
        settings.WEBHOOK_SECRET.encode(),
        signed_content,
        hashlib.sha256,
    ).hexdigest()


def _parse_output_text(raw: str | None) -> dict:
    """Parse output_text JSON string into output/error_output dict.

    Mirrors routes.py:_parse_output_text — duplicated to avoid agent→api import.
    """
    if not raw:
        return {"output": "", "error_output": ""}
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "output" in obj:
            return {
                "output": obj.get("output", ""),
                "error_output": obj.get("error_output", ""),
            }
    except (ValueError, TypeError):
        pass
    return {"output": raw, "error_output": ""}


def build_webhook_payload(
    *,
    job_id: str,
    status: str,
    payload: dict,
    price_usdc: float,
    submitter_address: str | None,
    submitted_at: datetime | None,
    compute_duration_s: float,
) -> dict:
    """Build the webhook JSON body from job data."""
    parsed = _parse_output_text(payload.get("output_text"))

    result: dict = {
        "webhook_event": f"job.{status}",
        "job_id": job_id,
        "status": status,
        "submitter_address": submitter_address,
        "price_usdc": price_usdc,
        "submitted_at": submitted_at.isoformat() if submitted_at else None,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "compute_duration_s": compute_duration_s,
        "image": payload.get("image"),
        "cpus": payload.get("cpus"),
        "output": parsed["output"],
        "error_output": parsed["error_output"],
    }

    if status == "failed":
        result["failure_reason"] = payload.get("failure_reason")
        result["fault"] = payload.get("fault")

    credit = payload.get("credit_applied")
    if credit:
        result["credit_applied"] = credit

    return result


async def deliver_webhook(url: str, payload: dict, event_bus=None) -> None:
    """POST payload to url with retries. Fire-and-forget safe (catches all exceptions)."""
    job_id_short = payload.get("job_id", "?")[:8]
    delivery_id = str(uuid.uuid4())

    try:
        body = json.dumps(payload, default=str).encode()
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))

        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Ouro-Delivery": delivery_id,
            "X-Ouro-Timestamp": timestamp,
        }
        sig = _sign_payload(timestamp, body)
        if sig:
            headers["X-Ouro-Signature-256"] = f"sha256={sig}"

        async with httpx.AsyncClient() as client:
            for attempt in range(1 + MAX_RETRIES):
                try:
                    resp = await client.post(
                        url,
                        content=body,
                        headers=headers,
                        timeout=TIMEOUT_SECONDS,
                        follow_redirects=False,
                    )
                    if resp.status_code < 400:
                        logger.info(
                            "Webhook delivered to %s (status %d, job %s, delivery %s)",
                            url, resp.status_code, job_id_short, delivery_id[:8],
                        )
                        if event_bus:
                            event_bus.emit("webhook", f"Webhook delivered for job {job_id_short}", job_id=payload.get("job_id"))
                        return
                    resp_body = resp.text[:200] if resp.text else ""
                    logger.warning(
                        "Webhook to %s returned %d (attempt %d/%d): %s",
                        url, resp.status_code, attempt + 1, 1 + MAX_RETRIES, resp_body,
                    )
                except Exception as e:
                    logger.warning(
                        "Webhook to %s failed (attempt %d/%d): %s",
                        url, attempt + 1, 1 + MAX_RETRIES, e,
                    )

                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAYS[attempt])

        logger.error(
            "Webhook delivery failed after %d attempts: %s (job %s, delivery %s)",
            1 + MAX_RETRIES, url, job_id_short, delivery_id[:8],
        )
        if event_bus:
            event_bus.emit("webhook", f"Webhook delivery failed for job {job_id_short} after {1 + MAX_RETRIES} attempts", job_id=payload.get("job_id"))
    except Exception:
        logger.exception("Unexpected error in webhook delivery to %s", url)
