"""Password validation and salted PBKDF2-HMAC-SHA256 hashing."""

import hashlib
import hmac
import secrets

ITERATIONS = 600_000


def password_is_valid(password):
    return (len(password) >= 8 and
            any(char.isalpha() for char in password) and
            any(char.isdigit() for char in password))


def password_fields(password):
    """Never store or log the input password itself."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return {"salt": salt.hex(), "password_hash": digest.hex(), "iterations": ITERATIONS}


def verify_password(password, user):
    try:
        salt = bytes.fromhex(user["salt"])
        expected = bytes.fromhex(user["password_hash"])
        iterations = int(user["iterations"])
        if len(salt) < 16 or len(expected) != 32 or not 1 <= iterations <= 2_000_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, KeyError, OverflowError):
        return False
