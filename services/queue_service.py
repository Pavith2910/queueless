"""
queue_service.py - Reads live queue data from MongoDB and turns it into
ready-to-display information: estimated wait, crowd status and trend.
"""
from datetime import datetime, timedelta, timezone
from config import Config
from db import db
from services.wait_time import estimate_wait_minutes, crowd_status

IST = timezone(timedelta(hours=5, minutes=30))
UTC = timezone.utc
TREND_WINDOW_MIN = 120        # how much recent history to send for the mini chart

# Fields every location has. Anything else is a category-specific extra
# (menu_tags, total_seats, ...) - the flexible part of the schema.
COMMON_FIELDS = {
    "location_id", "name", "category", "group", "opening_hours",
    "available_services", "default_counters", "default_service_seconds",
    "closed_on", "live", "trend","walk_minutes",
}


def now_ist():
    """Current Indian time. If DEMO_TIME is set in .env, pretend it is that time today."""
    now = datetime.now(IST)
    if Config.DEMO_TIME:
        hour, minute = map(int, Config.DEMO_TIME.split(":"))
        now = now.replace(hour=hour, minute=minute)
    return now


def is_open_now(loc, now):
    """Open if today is not a closed day and the time is within opening hours."""
    if now.strftime("%A") in loc.get("closed_on", []):
        return False
    hhmm = now.strftime("%H:%M")      # "HH:MM" strings compare correctly
    return loc["opening_hours"]["open"] <= hhmm < loc["opening_hours"]["close"]


def _trend_direction(trend):
    """Compares the latest snapshot with one about 30 minutes earlier."""
    if len(trend) < 2:
        return "steady"
    latest = trend[-1]
    cutoff = latest["t"] - timedelta(minutes=30)
    earlier = next((p for p in trend if p["t"] >= cutoff), trend[0])
    change = latest["w"] - earlier["w"]
    if change >= 3:
        return "rising"
    if change <= -3:
        return "falling"
    return "steady"


def _queue_pipeline(match=None):
    """Aggregation that joins each location with its live status and recent events."""
    since = datetime.now(UTC) - timedelta(minutes=TREND_WINDOW_MIN)
    pipeline = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        # JOIN 1: the live status document for this location
        {"$lookup": {
            "from": "queue_status",
            "localField": "location_id",
            "foreignField": "location_id",
            "as": "live",
        }},
        {"$unwind": "$live"},             # array of one -> single embedded object
        # JOIN 2: only the recent snapshots, via a sub-pipeline
        {"$lookup": {
            "from": "queue_events",
            "localField": "location_id",
            "foreignField": "location_id",
            "pipeline": [
                {"$match": {"event_type": "queue_update", "timestamp": {"$gte": since}}},
                {"$sort": {"timestamp": 1}},
                {"$project": {"_id": 0, "t": "$timestamp", "w": "$waiting_count"}},
            ],
            "as": "trend",
        }},
        {"$project": {"_id": 0, "live._id": 0}},
        {"$sort": {"category": 1, "name": 1}},
    ]
    return pipeline


def _to_card(doc, now):
    """Converts one aggregated document into the JSON the frontend needs."""
    live = doc["live"]
    open_now = is_open_now(doc, now)
    counters = live["active_counters"] or doc.get("default_counters", 1)
    waiting = live["current_waiting"] if open_now else 0
    wait = (estimate_wait_minutes(waiting, live["avg_service_seconds"], counters)
            if open_now else None)
    trend = doc.get("trend", [])
    updated = live["updated_at"]

    return {
        "location_id": doc["location_id"],
        "name": doc["name"],
        "category": doc["category"],
        "group": doc["group"],
        "services": doc["available_services"],
        "opening_hours": doc["opening_hours"],
        "extras": {k: v for k, v in doc.items() if k not in COMMON_FIELDS},
        "is_open": open_now,
        "waiting": waiting,
        "counters": counters if open_now else 0,
        "avg_service_seconds": live["avg_service_seconds"],
        "est_wait_min": wait,
        "status": crowd_status(wait, open_now),
        "trend_direction": _trend_direction(trend),
        "trend": [{"t": p["t"].isoformat(), "w": p["w"]} for p in trend],
        "updated_at": updated.isoformat(),
        "minutes_since_update": int((datetime.now(UTC) - updated).total_seconds() // 60),
    }


def _today_summary(location_id):
    """Today's statistics for one location, calculated by MongoDB."""
    midnight = now_ist().replace(hour=0, minute=0, second=0, microsecond=0)
    result = list(db.queue_events.aggregate([
        {"$match": {"location_id": location_id,
                    "timestamp": {"$gte": midnight.astimezone(UTC)}}},
        {"$group": {
            "_id": None,
            "served": {"$sum": {"$cond": [
                {"$eq": ["$event_type", "service_completed"]}, 1, 0]}},
            "avg_service": {"$avg": "$service_duration_seconds"},  # ignores missing values
            "peak_waiting": {"$max": "$waiting_count"},
        }},
    ]))
    if not result:
        return {"served": 0, "avg_service_seconds": None, "peak_waiting": 0}
    r = result[0]
    return {
        "served": r["served"],
        "avg_service_seconds": round(r["avg_service"], 1) if r["avg_service"] else None,
        "peak_waiting": r["peak_waiting"],
    }


def get_all_queues():
    now = now_ist()
    return [_to_card(doc, now) for doc in db.locations.aggregate(_queue_pipeline())]


def get_queue(location_id):
    docs = list(db.locations.aggregate(_queue_pipeline({"location_id": location_id})))
    if not docs:
        return None
    card = _to_card(docs[0], now_ist())
    card["today"] = _today_summary(location_id)
    return card