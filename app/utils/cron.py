"""Cron expression parsing utility."""

from apscheduler.triggers.cron import CronTrigger


def parse_cron(cron_expr: str) -> CronTrigger:
    """Parse a 5-field cron expression into a CronTrigger.

    Supports standard 5-field format: minute hour day month day_of_week.
    If only 2 fields are provided (minute hour), defaults to daily execution.

    Raises ValueError if fewer than 2 fields are given.
    """
    parts = cron_expr.strip().split()
    if len(parts) < 2:
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
        kwargs["day_of_week"] = parts[4]

    return CronTrigger(**kwargs)
