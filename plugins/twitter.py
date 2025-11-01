from cloudbot import hook


@hook.command("twitter", "tw", "twatter")
def twitter() -> str:  # pragma: no cover
    """- The Twitter API is no longer available."""

    return "The Twitter API is no longer available."


@hook.command("twuser", "twinfo")
def twuser() -> str:  # pragma: no cover
    """- The Twitter API is no longer available."""

    return "The Twitter API is no longer available."
