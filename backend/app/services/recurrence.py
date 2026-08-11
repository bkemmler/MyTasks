from __future__ import annotations

import logging
from datetime import datetime

from dateutil.rrule import rrulestr

logger = logging.getLogger(__name__)


def compute_next_occurrence(
    rrule_str: str,
    after: datetime,
) -> datetime | None:
    """Berechnet das nächste Vorkommen einer RRULE nach `after`.

    Returns None, wenn die RRULE erschöpft ist oder ungültig.
    """
    try:
        rule = rrulestr(rrule_str, dtstart=after)
    except Exception as e:
        logger.warning("Invalid RRULE %r: %s", rrule_str, e)
        return None
    try:
        next_dt = rule.after(after, inc=False)
    except Exception as e:
        logger.warning("RRULE.after failed for %r: %s", rrule_str, e)
        return None
    return next_dt
