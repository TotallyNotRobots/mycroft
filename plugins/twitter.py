from cloudbot import hook


@hook.command("twitter", "tw", "twatter")
def twitter(text, reply, conn) -> str:
    """- The Twitter API is no longer available."""

    return "The Twitter API is no longer available."


@hook.command("twuser", "twinfo")
def twuser(text, reply) -> str:
    """- The Twitter API is no longer available."""

    return "The Twitter API is no longer available."
