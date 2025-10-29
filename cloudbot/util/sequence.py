"""
Sequence utilities - Various util functions for working with lists, sets, tuples, etc
"""

from collections.abc import Generator, Sequence
from typing import TypeVar

_T = TypeVar("_T")


def chunk_iter(
    data: Sequence[_T], chunk_size: int
) -> Generator[Sequence[_T], None, None]:
    """
    Splits a sequence in to chunks

    :param data: The sequence to split
    :param chunk_size: The maximum size of each chunk
    :return: An iterable of all the chunks of the sequence
    """
    for i in range(0, len(data), chunk_size):
        yield data[i : i + chunk_size]
