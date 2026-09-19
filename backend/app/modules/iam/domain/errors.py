"""IAM domain errors."""


class DuplicateEmailError(Exception):
    """Registration attempted with an already-registered email."""


class InvalidCredentialsError(Exception):
    """Generic authentication failure; never distinguishes the cause."""


class JwtConfigurationError(Exception):
    """JWT settings missing or blank; token issue/verify must fail closed."""


class InvalidTokenError(Exception):
    """Generic token verification failure; never exposes claim details."""
