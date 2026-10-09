"""
wait_time.py - The waiting-time formula and crowd-status rules.
Used by the data generator, the APIs and the dashboard.

Estimated wait (minutes) = (N x S) / (C x 60)
    N = people ahead in the queue
    S = average service time per person (seconds)
    C = number of active counters
"""

LOW_MAX_MIN = 5         # under 5 min         -> "low"
MODERATE_MAX_MIN = 15   # 5 to under 15 min   -> "moderate", 15+ -> "busy"


def estimate_wait_minutes(people_ahead, avg_service_seconds, active_counters):
    """Returns the estimated wait in minutes, or None if no counter is open."""
    if active_counters <= 0:
        return None
    minutes = (people_ahead * avg_service_seconds) / (active_counters * 60)
    return round(minutes, 1)


def crowd_status(wait_minutes, is_open=True):
    """Converts an estimated wait into a simple crowd label."""
    if not is_open or wait_minutes is None:
        return "closed"
    if wait_minutes < LOW_MAX_MIN:
        return "low"
    if wait_minutes < MODERATE_MAX_MIN:
        return "moderate"
    return "busy"