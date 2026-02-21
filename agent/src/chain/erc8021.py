"""ERC-8021 Builder Code suffix encoder/decoder.

Format (parsed backward from end of calldata):
  schemaData + schemaId(0x00) + ercMarker(16 bytes)

For schema 0:
  schemaData = codesJoined(ASCII) + codesLength(1 byte)
  codesJoined = codes joined by comma (e.g. "ouro,morpho")
  codesLength = byte length of codesJoined
"""

ERC_MARKER = bytes.fromhex("80218021802180218021802180218021")
SCHEMA_ID = b"\x00"


def encode_builder_codes(codes: list[str]) -> bytes:
    codes_joined = ",".join(codes).encode("ascii")
    codes_length = len(codes_joined).to_bytes(1, "big")
    return codes_joined + codes_length + SCHEMA_ID + ERC_MARKER


def append_builder_codes(calldata: bytes, codes: list[str]) -> bytes:
    return calldata + encode_builder_codes(codes)


def decode_builder_codes(calldata: bytes) -> list[str] | None:
    if len(calldata) < 18:
        return None
    if calldata[-16:] != ERC_MARKER:
        return None
    schema_id = calldata[-17]
    if schema_id != 0:
        return None
    codes_length = calldata[-18]
    codes_start = len(calldata) - 18 - codes_length
    codes_bytes = calldata[codes_start : codes_start + codes_length]
    return codes_bytes.decode("ascii").split(",")
