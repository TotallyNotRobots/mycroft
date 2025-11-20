"""
Sequence utilities - Various util functions for working with lists, sets, tuples, etc
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

_T = TypeVar("_T")


def chunk_iter(data: Sequence[_T], chunk_size: int) -> Generator[Sequence[_T]]:
    """
    Splits a sequence in to chunks

    :param data: The sequence to split
    :param chunk_size: The maximum size of each chunk
    :return: An iterable of all the chunks of the sequence
    """
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]
