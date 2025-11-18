from __future__ import annotations

from typing import TYPE_CHECKING

from cloudbot import hook

if TYPE_CHECKING:
    from collections.abc import Callable


class Game:
    __slots__ = ("cmds", "name")

    def __init__(self, *cmds, name=None) -> None:
        self.cmds = cmds
        if name is None:
            name = cmds[0]

        self.name = name


GAMES = (
    Game("nfl"),
    Game("mlb"),
    Game("nba"),
    Game("ncb", "ncaab"),
    Game("ncf", "ncaaf"),
    Game("nhl"),
    Game("wnba"),
)


@hook.command("morescore", autohelp=False)
def morescore() -> str:  # pragma: no cover
    """- This API has been shut down."""
    return "This API has been shut down."


def score_hook(game: Game) -> Callable[[], str]:  # pragma: no cover
    def func() -> str:
        return "This API has been removed."

    func.__name__ = f"{game.name}_scores"
    func.__doc__ = "- This API has been removed."
    return func


def init_hooks() -> None:  # pragma: no cover
    for game in GAMES:
        func = score_hook(game)
        globals()[func.__name__] = hook.command(*game.cmds, autohelp=False)(
            func
        )


init_hooks()
