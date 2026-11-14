"""Formatting durations for display."""


def format_duration(hours: float) -> str:
    """Hours as ``<hours>h <minutes>m``, rounded to the nearest minute: ``5h 07m``."""
    whole, minutes = divmod(round(hours * 60), 60)
    return f"{whole}h {minutes:02d}m"
