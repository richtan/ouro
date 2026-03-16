"""Tests for EIP-191 wallet signature authentication."""
import time

import pytest
from fastapi import HTTPException
from eth_account import Account
from eth_account.messages import encode_defunct

# Test wallet
_TEST_KEY = "0x" + "ab" * 32
_TEST_ACCOUNT = Account.from_key(_TEST_KEY)
TEST_WALLET = _TEST_ACCOUNT.address.lower()


def _sign(message: str) -> str:
    msg = encode_defunct(text=message)
    return _TEST_ACCOUNT.sign_message(msg).signature.hex()


class TestVerifyWalletSignature:
    """Tests for the shared _verify_wallet_signature helper."""

    def test_valid_signature(self):
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()))
        msg = f"ouro-storage-list:{TEST_WALLET}:{ts}"
        sig = _sign(msg)
        _verify_wallet_signature(TEST_WALLET, msg, sig, ts)  # should not raise

    def test_expired_timestamp_rejected(self):
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()) - 600)  # 10 min ago
        msg = f"ouro-storage-list:{TEST_WALLET}:{ts}"
        sig = _sign(msg)
        with pytest.raises(HTTPException) as exc:
            _verify_wallet_signature(TEST_WALLET, msg, sig, ts)
        assert exc.value.status_code == 401
        assert "expired" in str(exc.value.detail).lower()

    def test_wrong_wallet_rejected(self):
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()))
        other = "0x" + "00" * 20
        msg = f"ouro-storage-list:{other}:{ts}"
        sig = _sign(msg)  # signed by TEST_WALLET, verified against other
        with pytest.raises(HTTPException) as exc:
            _verify_wallet_signature(other, msg, sig, ts)
        assert exc.value.status_code == 401
        assert "does not match" in str(exc.value.detail).lower()

    def test_garbage_signature_rejected(self):
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()))
        msg = f"ouro-storage-list:{TEST_WALLET}:{ts}"
        with pytest.raises(HTTPException) as exc:
            _verify_wallet_signature(TEST_WALLET, msg, "0xdeadbeef", ts)
        assert exc.value.status_code == 401

    def test_invalid_timestamp_rejected(self):
        from src.api.routes import _verify_wallet_signature

        with pytest.raises(HTTPException) as exc:
            _verify_wallet_signature(TEST_WALLET, "msg", "0x00", "notanumber")
        assert exc.value.status_code == 401

    def test_future_timestamp_within_window(self):
        """Timestamps slightly in the future are OK (clock skew)."""
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()) + 60)  # 1 min in future
        msg = f"ouro-storage-list:{TEST_WALLET}:{ts}"
        sig = _sign(msg)
        _verify_wallet_signature(TEST_WALLET, msg, sig, ts)  # should not raise

    def test_different_actions_not_interchangeable(self):
        """A storage-list signature cannot be used for storage-delete."""
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()))
        list_msg = f"ouro-storage-list:{TEST_WALLET}:{ts}"
        delete_msg = f"ouro-storage-delete:{TEST_WALLET}:file.txt:{ts}"
        list_sig = _sign(list_msg)
        with pytest.raises(HTTPException):
            _verify_wallet_signature(TEST_WALLET, delete_msg, list_sig, ts)

    def test_job_view_signature(self):
        """Job view signatures work correctly."""
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()))
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        msg = f"ouro-job-view:{job_id}:{TEST_WALLET}:{ts}"
        sig = _sign(msg)
        _verify_wallet_signature(TEST_WALLET, msg, sig, ts)

    def test_job_events_signature(self):
        """Job events signatures work correctly."""
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()))
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        msg = f"ouro-job-events:{job_id}:{TEST_WALLET}:{ts}"
        sig = _sign(msg)
        _verify_wallet_signature(TEST_WALLET, msg, sig, ts)

    def test_job_view_sig_cannot_access_events(self):
        """A job-view signature cannot be used for job-events."""
        from src.api.routes import _verify_wallet_signature

        ts = str(int(time.time()))
        job_id = "550e8400-e29b-41d4-a716-446655440000"
        view_msg = f"ouro-job-view:{job_id}:{TEST_WALLET}:{ts}"
        events_msg = f"ouro-job-events:{job_id}:{TEST_WALLET}:{ts}"
        view_sig = _sign(view_msg)
        with pytest.raises(HTTPException):
            _verify_wallet_signature(TEST_WALLET, events_msg, view_sig, ts)
