"""
scene.py

Provides commands for searching scene releases using orlydb.com.

Created By:
    - Ryan Hitchman <https://github.com/rmmh>

Modified By:
    - Luke Rogers <https://github.com/lukeroge>

License:
    GPL v3
"""

from cloudbot import hook


@hook.command("pre", "scene")
def pre() -> str:  # pragma: no cover
    """- This command has been removed, orlydb.com is down permanently."""

    return "This command has been removed, orlydb.com is down permanently."
