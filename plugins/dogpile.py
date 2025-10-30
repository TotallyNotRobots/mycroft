from cloudbot import hook


@hook.command("dpis", "gis")
def dogpileimage() -> str:  # pragma: no cover
    """- This command is no longer supported."""
    return "This command is no longer supported."


@hook.command("dp", "g", "dogpile")
def dogpile() -> str:  # pragma: no cover
    """- This command is no longer supported."""
    return "This command is no longer supported."
