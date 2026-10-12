"""Cron expression parsing utility."""

from apscheduler.triggers.cron import CronTrigger


def _weekday_field(field: str) -> str:
    """Translate Unix Sunday=0/7 to APScheduler's Monday=0 convention."""
    names = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
    translated = []
    for part in field.split(","):
        if any(character.isalpha() for character in part) or part == "*":
            translated.append(part)
            continue
        base, _, step_text = part.partition("/")
        step = int(step_text) if step_text else 1
        if step < 1:
            raise ValueError("Weekday step must be positive")
        if base == "*":
            start, end = 0, 6
        elif "-" in base:
            start, end = map(int, base.split("-"))
        else:
            start = int(base)
            end = 7 if step_text else start
        if not 0 <= start <= end <= 7:
            raise ValueError("Unix weekday must be in 0..7")
        translated.extend(names[number % 7] for number in range(start, end + 1, step))
    return ",".join(dict.fromkeys(translated))


def parse_cron(cron_expr: str) -> CronTrigger:
    """Parse a 5-field cron expression into a CronTrigger.

    Supports standard 5-field format: minute hour day month day_of_week.
    If only 2 fields are provided (minute hour), defaults to daily execution.

    Raises ValueError if fewer than 2 fields are given.
    """
    parts = cron_expr.strip().split()
    if not 2 <= len(parts) <= 5:
        raise ValueError(
            f"Cron expression needs at least 2 fields (minute hour), got: {cron_expr}"
        )

    kwargs = {
        "minute": parts[0],
        "hour": parts[1],
    }
    if len(parts) > 2:
        kwargs["day"] = parts[2]
    if len(parts) > 3:
        kwargs["month"] = parts[3]
    if len(parts) > 4:
        kwargs["day_of_week"] = _weekday_field(parts[4])

    return CronTrigger(**kwargs)
