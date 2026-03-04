"""Tests for ERC-8021 Builder Code encoder/decoder."""

from src.chain.erc8021 import (
    ERC_MARKER,
    append_builder_codes,
    decode_builder_codes,
    encode_builder_codes,
)


def test_encode_single_code():
    result = encode_builder_codes(["ouro"])
    # Structure: "ouro" (4 bytes) + length (1 byte = 0x04) + schema (0x00) + marker (16 bytes)
    assert result == b"ouro" + b"\x04" + b"\x00" + ERC_MARKER


def test_encode_multiple_codes():
    result = encode_builder_codes(["ouro", "morpho"])
    codes_joined = b"ouro,morpho"  # 11 bytes
    assert result == codes_joined + b"\x0b" + b"\x00" + ERC_MARKER


def test_decode_single_code():
    encoded = encode_builder_codes(["ouro"])
    assert decode_builder_codes(encoded) == ["ouro"]


def test_decode_multiple_codes():
    encoded = encode_builder_codes(["ouro", "morpho"])
    assert decode_builder_codes(encoded) == ["ouro", "morpho"]


def test_decode_short_data_returns_none():
    assert decode_builder_codes(b"\x00" * 17) is None


def test_decode_missing_marker_returns_none():
    data = b"ouro" + b"\x04" + b"\x00" + b"\x00" * 16
    assert decode_builder_codes(data) is None


def test_decode_wrong_schema_returns_none():
    codes_joined = b"ouro"
    # Use schema_id=0x01 instead of 0x00
    data = codes_joined + b"\x04" + b"\x01" + ERC_MARKER
    assert decode_builder_codes(data) is None


def test_append_preserves_prefix():
    prefix = b"\xff\xff"
    result = append_builder_codes(prefix, ["ouro"])
    assert result[:2] == prefix
    assert decode_builder_codes(result) == ["ouro"]


def test_roundtrip_with_calldata():
    calldata = b"\x01\x02\x03\x04"
    combined = append_builder_codes(calldata, ["ouro", "base"])
    decoded = decode_builder_codes(combined)
    assert decoded == ["ouro", "base"]


def test_encode_empty_codes():
    result = encode_builder_codes([])
    # Empty codes_joined = b"", length = 0
    assert result == b"" + b"\x00" + b"\x00" + ERC_MARKER
    # Decoding empty codes produces [""] due to split(",") on empty string
    decoded = decode_builder_codes(result)
    assert decoded == [""]


def test_encode_long_code_overflow():
    """Code > 255 bytes overflows the 1-byte length field."""
    long_code = "a" * 256
    import pytest

    with pytest.raises(OverflowError):
        encode_builder_codes([long_code])


def test_decode_exact_18_bytes():
    """Exactly 18 bytes with valid structure (0-length codes) → decodes."""
    # 0 bytes of codes + length=0x00 + schema=0x00 + 16-byte marker = 18 bytes
    data = b"\x00" + b"\x00" + ERC_MARKER
    result = decode_builder_codes(data)
    assert result == [""]
