from cloudbot import hook


@hook.command("mcuser", "mcpaid", "haspaid")
def mcuser() -> str:  # pragma: no cover
    """- This API has been shut down."""
    return "This API has been shut down."
