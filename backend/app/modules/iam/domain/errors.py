"""IAM domain errors."""


class DuplicateEmailError(Exception):
    """Registration attempted with an already-registered email."""


class InvalidCredentialsError(Exception):
    """Generic authentication failure; never distinguishes the cause."""
