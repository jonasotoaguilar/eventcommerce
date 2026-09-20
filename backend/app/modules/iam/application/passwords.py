"""Password hashing service (Argon2id via official pwdlib)."""

from pwdlib import PasswordHash

_hash = PasswordHash.recommended()

# Valid dummy hash so unknown-user authentication still performs one
# verification and does not leak account existence through timing.
DUMMY_HASH: str = _hash.hash("iam-dummy-credential")


def hash_password(password: str) -> str:
    """Hash a password with the recommended Argon2id parameters."""
    return _hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password; malformed stored hashes fail closed as False."""
    try:
        return bool(_hash.verify(password, password_hash))
    except Exception:
        return False
