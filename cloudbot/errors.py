import inspect


class ShouldBeUnreachable(RuntimeError):
    def __init__(self) -> None:
        current_frame = inspect.currentframe()
        if current_frame is None:
            raise ValueError("Missing current frame")

        outer_frame = current_frame.f_back
        if outer_frame is None:
            raise ValueError("Missing outer frame")

        super().__init__(
            f"A branch that should be unreachable has been reached at {outer_frame.f_code.co_filename}:{outer_frame.f_lineno}. THIS IS A BUG. Please report it right away on the issue tracker at https://github.com/TotallyNotRobots/CloudBot/issues/new"
        )
