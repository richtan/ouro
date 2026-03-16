"""Tests for webhook delivery and payload construction."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.webhooks import (
    _sign_payload,
    build_webhook_payload,
    deliver_webhook,
)


# --- build_webhook_payload ---


def test_build_payload_completed():
    payload = build_webhook_payload(
        job_id="abc-123",
        status="completed",
        payload={
            "image": "ouro-python",
            "cpus": 2,
            "output_text": json.dumps({"output": "hello", "error_output": ""}),
        },
        price_usdc=0.015,
        submitter_address="0xuser",
        submitted_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=timezone.utc),
        compute_duration_s=83.2,
    )
    assert payload["webhook_event"] == "job.completed"
    assert payload["job_id"] == "abc-123"
    assert payload["status"] == "completed"
    assert payload["output"] == "hello"
    assert payload["cpus"] == 2
    assert payload["image"] == "ouro-python"
    assert payload["price_usdc"] == 0.015
    assert payload["compute_duration_s"] == 83.2
    assert "failure_reason" not in payload
    assert "fault" not in payload


def test_build_payload_failed():
    payload = build_webhook_payload(
        job_id="def-456",
        status="failed",
        payload={
            "image": "ouro-ubuntu",
            "cpus": 1,
            "failure_reason": "exit code 1",
            "fault": "user_error",
        },
        price_usdc=0.01,
        submitter_address="0xuser",
        submitted_at=datetime(2026, 3, 13, 10, 0, 0, tzinfo=timezone.utc),
        compute_duration_s=5.0,
    )
    assert payload["webhook_event"] == "job.failed"
    assert payload["failure_reason"] == "exit code 1"
    assert payload["fault"] == "user_error"


def test_build_payload_with_credit():
    payload = build_webhook_payload(
        job_id="ghi-789",
        status="completed",
        payload={"image": "ouro-ubuntu", "cpus": 1, "credit_applied": 0.005},
        price_usdc=0.01,
        submitter_address="0xuser",
        submitted_at=None,
        compute_duration_s=10.0,
    )
    assert payload["credit_applied"] == 0.005


def test_build_payload_no_output():
    payload = build_webhook_payload(
        job_id="jkl-000",
        status="completed",
        payload={"image": "ouro-ubuntu", "cpus": 1},
        price_usdc=0.01,
        submitter_address=None,
        submitted_at=None,
        compute_duration_s=0,
    )
    assert payload["output"] == ""
    assert payload["error_output"] == ""
    assert payload["submitter_address"] is None


# --- _sign_payload ---


def test_sign_payload_with_secret():
    with patch("src.agent.webhooks.settings") as mock_settings:
        mock_settings.WEBHOOK_SECRET = "test-secret"
        body = b'{"job_id": "abc"}'
        timestamp = "1710345600"
        sig = _sign_payload(timestamp, body)
        signed_content = f"{timestamp}.".encode() + body
        expected = hmac.new(b"test-secret", signed_content, hashlib.sha256).hexdigest()
        assert sig == expected


def test_sign_payload_no_secret():
    with patch("src.agent.webhooks.settings") as mock_settings:
        mock_settings.WEBHOOK_SECRET = ""
        assert _sign_payload("1710345600", b"anything") is None


# --- deliver_webhook ---


async def test_deliver_success():
    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("src.agent.webhooks.httpx.AsyncClient") as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await deliver_webhook("https://example.com/hook", {"job_id": "abc"})

        client_instance.post.assert_awaited_once()
        call_kwargs = client_instance.post.call_args
        assert call_kwargs[1]["follow_redirects"] is False
        headers = call_kwargs[1]["headers"]
        assert headers["User-Agent"] == "Ouro-Webhook/1.0"
        assert "X-Ouro-Delivery" in headers
        assert "X-Ouro-Timestamp" in headers


async def test_deliver_retry_on_500():
    mock_response = AsyncMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    with patch("src.agent.webhooks.httpx.AsyncClient") as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("src.agent.webhooks.RETRY_DELAYS", [0, 0]):
            await deliver_webhook("https://example.com/hook", {"job_id": "abc"})

        assert client_instance.post.await_count == 3  # 1 initial + 2 retries


async def test_deliver_retry_on_exception():
    with patch("src.agent.webhooks.httpx.AsyncClient") as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.post.side_effect = Exception("connection refused")
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("src.agent.webhooks.RETRY_DELAYS", [0, 0]):
            await deliver_webhook("https://example.com/hook", {"job_id": "abc"})

        assert client_instance.post.await_count == 3


async def test_deliver_no_retry_on_success():
    mock_response = AsyncMock()
    mock_response.status_code = 201

    with patch("src.agent.webhooks.httpx.AsyncClient") as mock_client_cls:
        client_instance = AsyncMock()
        client_instance.post.return_value = mock_response
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await deliver_webhook("https://example.com/hook", {"job_id": "abc"})

        assert client_instance.post.await_count == 1


# --- URL validation (tested via routes import) ---


def test_validate_webhook_url_rejects_http():
    from src.api.routes import _validate_webhook_url
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _validate_webhook_url("http://example.com/hook")
    assert exc_info.value.status_code == 422
    assert "HTTPS" in str(exc_info.value.detail)


def test_validate_webhook_url_allows_localhost_http():
    from src.api.routes import _validate_webhook_url

    _validate_webhook_url("http://localhost:9999/hook")
    _validate_webhook_url("http://127.0.0.1:8080/hook")


def test_validate_webhook_url_rejects_no_scheme():
    from src.api.routes import _validate_webhook_url
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _validate_webhook_url("not-a-url")
    assert exc_info.value.status_code == 422


def test_validate_webhook_url_rejects_empty_netloc():
    from src.api.routes import _validate_webhook_url
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        _validate_webhook_url("https://")
    assert exc_info.value.status_code == 422


def test_validate_webhook_url_rejects_ftp():
    from src.api.routes import _validate_webhook_url
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        _validate_webhook_url("ftp://example.com/hook")


def test_validate_webhook_url_allows_https():
    from src.api.routes import _validate_webhook_url

    _validate_webhook_url("https://example.com/hook")
    _validate_webhook_url("https://hooks.myapp.io/ouro?token=abc")
