from __future__ import annotations

import os
import platform
import time
from datetime import timedelta

import psutil

from cloudbot import hook
from cloudbot.util.filesize import size as format_bytes


@hook.command(autohelp=False)
def system(reply, message) -> None:
    """- Retrieves information about the host system."""

    # Get general system info
    sys_os = platform.platform()
    python_implementation = platform.python_implementation()
    python_version = platform.python_version()
    sys_architecture = "-".join(platform.architecture())
    sys_cpu_count = platform.machine()

    reply(
        f"OS: \x02{sys_os}\x02, "
        f"Python: \x02{python_implementation} {python_version}\x02, "
        f"Architecture: \x02{sys_architecture}\x02 (\x02{sys_cpu_count}\x02)"
    )

    process = psutil.Process(os.getpid())

    # get the data we need using the Process we got
    cpu_usage = process.cpu_percent(1)
    thread_count = process.num_threads()
    memory_usage = format_bytes(process.memory_info()[0])
    uptime = timedelta(seconds=round(time.time() - process.create_time()))

    message(
        f"Uptime: \x02{uptime}\x02, "
        f"Threads: \x02{thread_count}\x02, "
        f"CPU Usage: \x02{cpu_usage}\x02, "
        f"Memory Usage: \x02{memory_usage}\x02"
    )
