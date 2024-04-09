from asyncio import AbstractEventLoop
import logging
import os
import random
from concurrent.futures import ThreadPoolExecutor

from cloudbot.util.async_util import create_future

logger = logging.getLogger("cloudbot")


class ExecutorWrapper:
    def __init__(self, pool, executor):
        self._pool = pool
        self._executor = executor

    def release(self):
        self._pool.release_executor(self._executor)
        self._executor = None

    @property
    def executor(self):
        return self._executor

    def __del__(self):
        self.release()


class ExecutorPool:
    def __init__(
        self, max_executors=None, executor_type=ThreadPoolExecutor, *, loop:AbstractEventLoop, **kwargs
    ) -> None:
        if max_executors is None:
            max_executors = (os.cpu_count() or 1) * 5

        if max_executors <= 0:
            raise ValueError("max_executors must be greater than 0")

        self._max = max_executors
        self._exec_class = executor_type
        self._exec_args = kwargs

        self._executors = []
        self._free_executors = []
        self._executor_waiter = create_future(loop)

    def get(self):
        return ExecutorWrapper(self, self._get())

    def _get(self):
        if not self._free_executors:
            if len(self._executors) < self._max:
                return self._add_executor()

            return random.choice(self._executors)

        return self._free_executors.pop()

    def release_executor(self, executor):
        self._free_executors.append(executor)

    def _add_executor(self):
        exc = self._exec_class(**self._exec_args)
        self._executors.append(exc)

        return exc
