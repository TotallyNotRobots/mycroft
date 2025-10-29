from cloudbot import hook


@hook.command()
def snopes() -> str:  # pragma: no cover
    """- This command has been removed as the search API has been shut down."""
    return "This command has been removed as the search API has been shut down"
