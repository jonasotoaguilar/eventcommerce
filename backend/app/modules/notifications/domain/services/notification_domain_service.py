"""Pure domain logic for notifications."""
SUPPORTED_CHANNELS = {"email", "sms", "push"}


def is_channel_supported(channel: str) -> bool:
    return channel in SUPPORTED_CHANNELS

