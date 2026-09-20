"""Password service tests (real Argon2id hasher, no secrets asserted)."""

from app.modules.iam.application.passwords import (
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_recommended_hasher_uses_argon2(self) -> None:
        assert hash_password("correct-horse-8").startswith("$argon2")

    def test_hash_verifies_with_correct_password(self) -> None:
        assert verify_password("correct-horse-8", hash_password("correct-horse-8"))

    def test_wrong_password_does_not_verify(self) -> None:
        assert not verify_password("wrong-password", hash_password("correct-horse-8"))

    def test_hash_never_embeds_plaintext(self) -> None:
        password = "correct-horse-8"
        assert hash_password(password) != password
        assert password not in hash_password(password)

    def test_same_password_yields_distinct_hashes(self) -> None:
        assert hash_password("correct-horse-8") != hash_password("correct-horse-8")

    def test_malformed_stored_hash_fails_closed(self) -> None:
        assert not verify_password("correct-horse-8", "not-a-valid-hash")
        assert not verify_password("correct-horse-8", "")
