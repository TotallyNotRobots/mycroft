from cloudbot import hook


@hook.command("fos", "fuckoff", "foaas", autohelp=False)
def foaas() -> str:  # pragma: no cover
    """- This API has been shut down."""
    return "This API has been shut down."
