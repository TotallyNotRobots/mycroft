from cloudbot import hook


@hook.command("shrug", autohelp=False)
def shrug():
    r"""- shrugs

    >>> shrug()
    '\xaf\\_(\u30c4)_/\xaf'
    """
    return "\xaf\\_(\u30c4)_/\xaf"
