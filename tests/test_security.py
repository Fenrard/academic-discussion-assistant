import jwt
import pytest

from backend.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_produces_a_bcrypt_hash():
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$2b$")
    assert hashed != "correct horse battery staple"


def test_verify_password_round_trip():
    hashed = hash_password("s3cr3t-password")
    assert verify_password("s3cr3t-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_hash_password_handles_long_input_without_raising():
    # bcrypt's own hard limit is 72 bytes — this must not raise (see the >72-byte
    # truncation in hash_password/verify_password), unlike passlib's CryptContext,
    # which raises ValueError on anything longer.
    long_password = "a" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed) is True
    # Differs within the first 72 bytes -> must NOT verify, even though both inputs
    # are >72 bytes and share the same length.
    different_within_limit = "b" + "a" * 199
    assert verify_password(different_within_limit, hashed) is False
    # Differs only *past* byte 72 -> both truncate to the same 72-byte prefix, so this
    # one correctly DOES verify — that's bcrypt's own documented truncation behavior,
    # not a bug in this wrapper.
    same_prefix_different_tail = "a" * 72 + "different-suffix"
    assert verify_password(same_prefix_different_tail, hashed) is True


def test_create_and_decode_access_token_round_trip():
    token = create_access_token(subject="user-123")
    assert decode_access_token(token) == "user-123"


def test_decode_access_token_rejects_tampered_token():
    token = create_access_token(subject="user-123")
    # Flip a character in the middle of the token (the payload segment), not the last
    # character of the whole token. A JWT's HMAC signature is 32 bytes, which base64url
    # -encodes to a final character carrying only 4 real bits (the other 2 are padding
    # zeros) — 4 of the 64 base64url characters decode to those same 4 bits, so tampering
    # with specifically the *last* character has a real ~1-in-4 chance of producing a
    # byte-for-byte identical signature (this was caught as a genuine intermittent
    # failure, not a hypothetical: the token's actual last character happened to be one
    # of those 4-way-equivalent ones). A middle character has no such equivalence class.
    middle = len(token) // 2
    tampered = token[:middle] + ("A" if token[middle] != "A" else "B") + token[middle + 1:]
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)


def test_access_token_default_expiry_is_reasonable():
    assert ACCESS_TOKEN_EXPIRE_MINUTES > 0
