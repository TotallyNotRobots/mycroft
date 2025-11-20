import random
import time


class Delayer:
    def __init__(self, base=1, *, integral=False) -> None:
        self._base = base
        self._integral = integral
        self._max = 10
        self._exp = 0
        self._rand = random.Random()

    @property
    def randfunc(self):
        return self._rand.randrange if self._integral else self._rand.uniform

    def __enter__(self):
        self._exp = min(self._exp + 1, self._max)
        wait = self.randfunc(0, self._base * (2**self._exp))
        time.sleep(wait)
        return self

    def __exit__(self, *exc) -> None:
        pass
