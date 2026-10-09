"""
staff_service.py - Write operations used by the staff panel.

Every action does TWO writes:
  1. updates the single live document in queue_status  (current state)
  2. inserts a new document into queue_events           (permanent history)
"""
from datetime import datetime, timezone

from pymongo import DESCENDING, ReturnDocument

from db import db
from services.queue_service import is_open_now, now_ist
from services.wait_time import estimate_wait_minutes, crowd_status

UTC = timezone.utc
RECENT_SERVICES = 20      # rolling average uses the last 20 services
MIN_GAP_SECONDS = 10      # taps faster than this are treated as bulk entry, not timing
MAX_GAP_SECONDS = 600     # longer gaps mean the counter was idle


class QueueError(Exception):
    """Raised for invalid staff actions (unknown location, empty queue, ...)."""


def _location(location_id):
    loc = db.locations.find_one({"location_id": location_id}, {"_id": 0})
    if loc is None:
        raise QueueError(f"Unknown location '{location_id}'")
    return loc


def _log_event(location_id, event_type, live, **extra):
    """WRITE 2: append a history event (never updated or deleted)."""
    db.queue_events.insert_one({
        "location_id": location_id,
        "event_type": event_type,
        "waiting_count": live["current_waiting"],
        "active_counters": live["active_counters"],
        "timestamp": datetime.now(UTC),
        **extra,
    })


def _refresh_status(loc, live):
    """Recalculate the crowd label and save it on the live document."""
    est = estimate_wait_minutes(live["current_waiting"],
                                live["avg_service_seconds"],
                                live["active_counters"])
    status = crowd_status(est, is_open_now(loc, now_ist()))
    db.queue_status.update_one({"location_id": loc["location_id"]},
                               {"$set": {"status": status}})


def _update_live(location_id, update):
    """WRITE 1: atomically change the live document and return the new version."""
    update.setdefault("$set", {})["updated_at"] = datetime.now(UTC)
    return db.queue_status.find_one_and_update(
        {"location_id": location_id}, update,
        return_document=ReturnDocument.AFTER,
    )


# ----------------------------------------------------------------- actions
def add_people(location_id, count):
    loc = _location(location_id)
    live = _update_live(location_id, {"$inc": {"current_waiting": count}})
    _log_event(location_id, "queue_update", live)
    _refresh_status(loc, live)


def set_waiting(location_id, waiting):
    loc = _location(location_id)
    live = _update_live(location_id, {"$set": {"current_waiting": waiting}})
    _log_event(location_id, "queue_update", live)
    _refresh_status(loc, live)


def set_counters(location_id, counters):
    loc = _location(location_id)
    live = _update_live(location_id, {"$set": {"active_counters": counters}})
    _log_event(location_id, "counter_change", live)
    _refresh_status(loc, live)


def serve_next(location_id):
    loc = _location(location_id)
    now = datetime.now(UTC)

    # Atomic conditional update: only decrease if someone is actually waiting.
    # Two staff clicking at once can never push the count below zero.
    live = db.queue_status.find_one_and_update(
        {"location_id": location_id, "current_waiting": {"$gt": 0}},
        {"$inc": {"current_waiting": -1}, "$set": {"updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if live is None:
        raise QueueError("Nobody is waiting - nothing to serve.")

    extra = {"served_count": _served_today(location_id) + 1}
    duration = _estimate_duration(location_id, live["active_counters"], now)
    if duration:
        extra["service_duration_seconds"] = duration
    _log_event(location_id, "service_completed", live, **extra)

    # Learn from recent services: update the average used by the formula
    new_avg = _recent_average(location_id)
    if new_avg:
        live = _update_live(location_id, {"$set": {"avg_service_seconds": new_avg}})
    _refresh_status(loc, live)


# ----------------------------------------------------------------- helpers
def _served_today(location_id):
    midnight = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.queue_events.count_documents({
        "location_id": location_id,
        "event_type": "service_completed",
        "timestamp": {"$gte": midnight.astimezone(UTC)},
    })


def _estimate_duration(location_id, counters, now):
    """
    With C counters working in parallel, a service finishes roughly every S / C
    seconds. So one person's service time S is about (gap between completions) x C.
    """
    last = db.queue_events.find_one(
        {"location_id": location_id, "event_type": "service_completed"},
        sort=[("timestamp", DESCENDING)],
    )
    if last is None:
        return None
    gap = (now - last["timestamp"]).total_seconds()
    if not (MIN_GAP_SECONDS <= gap <= MAX_GAP_SECONDS):
        return None
    return round(gap * max(counters, 1), 1)


def _recent_average(location_id):
    result = list(db.queue_events.aggregate([
        {"$match": {"location_id": location_id,
                    "event_type": "service_completed",
                    "service_duration_seconds": {"$exists": True}}},
        {"$sort": {"timestamp": -1}},
        {"$limit": RECENT_SERVICES},
        {"$group": {"_id": None, "avg": {"$avg": "$service_duration_seconds"}}},
    ]))
    return round(result[0]["avg"]) if result else None