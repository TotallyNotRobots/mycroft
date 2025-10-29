from cloudbot import hook


@hook.command("steamcalc", "steamdb")
def steamcalc() -> str:  # pragma: no cover
    """- This command has been removed due to lack of supported API."""
    return "This command has been removed due to lack of supported API."
