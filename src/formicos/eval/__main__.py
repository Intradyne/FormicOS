"""Allow ``python -m formicos.eval`` to show usage."""


def _dispatch() -> None:
    """Route to run or compare based on how the module was invoked."""
    print(  # noqa: T201
        "Usage:\n"
        "  python -m formicos.eval.run     --task TASK_ID --runs N\n"
        "  python -m formicos.eval.compare --task TASK_ID\n"
        "  python -m formicos.eval.run     --list\n"
    )


if __name__ == "__main__":
    _dispatch()
