"""Optimistic locking: clients send the version they edited as `If-Match: "<version>"`."""

from app.core.errors import ProblemError


def check_version(current: int, if_match: str | None, what: str = "item") -> None:
    if if_match is None:
        raise ProblemError(
            428, "precondition_required", "Version missing", f"Reload the {what} and try again."
        )
    if if_match.strip().removeprefix("W/").strip('"') != str(current):
        raise ProblemError(
            412,
            "stale_version",
            f"This {what} was changed by someone else",
            f"Reload the {what} and apply your changes again.",
        )
