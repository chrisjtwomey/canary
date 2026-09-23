"""GET /logs: the boards' log lines, for the Logs view to page through."""
from __future__ import annotations

from epd_server.logs import LEVELS, LogStore

# The most lines one answer carries, however many are asked for.
MAX_LINES = 500


def _number(args: dict, name: str) -> int | None:
    value = args.get(name)
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be a whole number") from None


class LogsQuery:
    """Answers ``/logs`` from ``store``, with times shown in ``tz``."""

    def __init__(self, store: LogStore, tz):
        self.store = store
        self.tz = tz

    def answer(self, args: dict) -> dict:
        """The lines ``args`` asks for, oldest first, and every board that has any.

        ``after`` or ``before`` a line's number pages forward or back; with
        neither, the newest. ``board``, ``level`` (that level and above) and
        ``q`` (text the line contains) narrow them; ``limit`` caps how many.

        Raises:
            ValueError: a number that is not one, or a level the boards do not send.
        """
        level = args.get("level") or None
        if level is not None and level not in LEVELS:
            raise ValueError(f"level must be one of {', '.join(LEVELS)}")
        limit = min(_number(args, "limit") or 200, MAX_LINES)
        lines = self.store.lines(after=_number(args, "after"), before=_number(args, "before"),
                                 board=args.get("board") or None,
                                 level=LEVELS.index(level) if level else None,
                                 contains=args.get("q") or None, limit=limit)
        return {"lines": lines, "boards": self.store.boards(),
                "tz": getattr(self.tz, "key", "UTC")}
