"""
analytics_service.py - Historical analytics using MongoDB aggregation pipelines.

Timestamps are stored in UTC. All hours and days are converted to Indian
time (Asia/Kolkata) INSIDE MongoDB using the 'timezone' option.
"""
import time
from datetime import datetime, timedelta, timezone

from db import db
from services.queue_service import now_ist
from services.wait_time import estimate_wait_minutes

TZ = "Asia/Kolkata"
UTC = timezone.utc
METRICS_MAX_AGE_MIN = 10      # recompute the cache if older than this
# MongoDB's $dayOfWeek: 1 = Sunday ... 7 = Saturday
DAY_NAMES = {1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat"}


def _ist(field):
    """Date-part options that make MongoDB use Indian time."""
    return {"date": field, "timezone": TZ}


def _with_location_name():
    """Pipeline stages that attach the location's name (a $lookup join)."""
    return [
        {"$lookup": {"from": "locations", "localField": "location_id",
                     "foreignField": "location_id", "as": "loc"}},
        {"$set": {"name": {"$first": "$loc.name"}}},
        {"$unset": "loc"},
    ]


# ------------------------------------------------------------------ cache
def refresh_service_metrics():
    """
    Precomputes averages per (location, day of week, hour) from ALL events
    and saves them into service_metrics using $merge (insert or replace).
    """
    started = time.perf_counter()
    is_snapshot = {"$eq": ["$event_type", "queue_update"]}
    list(db.queue_events.aggregate([
        {"$match": {"event_type": {"$in": ["queue_update", "service_completed"]}}},
        {"$group": {
            "_id": {
                "location_id": "$location_id",
                "day_of_week": {"$dayOfWeek": _ist("$timestamp")},
                "hour": {"$hour": _ist("$timestamp")},
            },
            # $avg / $max ignore nulls, so only snapshot events count here
            "avg_waiting": {"$avg": {"$cond": [is_snapshot, "$waiting_count", None]}},
            "max_waiting": {"$max": {"$cond": [is_snapshot, "$waiting_count", None]}},
            "svc": {"$avg": "$service_duration_seconds"},
            "sample_count": {"$sum": {"$cond": [is_snapshot, 1, 0]}},
        }},
        {"$match": {"avg_waiting": {"$ne": None}}},
        {"$project": {
            "_id": 0,
            "location_id": "$_id.location_id",
            "day_of_week": "$_id.day_of_week",
            "hour": "$_id.hour",
            "avg_waiting": {"$round": ["$avg_waiting", 2]},
            "max_waiting": 1,
            # leave the field out entirely if there were no services that hour
            "avg_service_seconds": {"$cond": [{"$eq": ["$svc", None]},
                                              "$$REMOVE", {"$round": ["$svc", 1]}]},
            "sample_count": 1,
            "computed_at": "$$NOW",
        }},
        {"$merge": {
            "into": "service_metrics",
            "on": ["location_id", "day_of_week", "hour"],   # uses our unique index
            "whenMatched": "replace",
            "whenNotMatched": "insert",
        }},
    ]))
    return {
        "documents": db.service_metrics.count_documents({}),
        "ms": round((time.perf_counter() - started) * 1000),
    }


def ensure_metrics_fresh():
    latest = db.service_metrics.find_one({}, sort=[("computed_at", -1)])
    too_old = latest and datetime.now(UTC) - latest["computed_at"] > timedelta(minutes=METRICS_MAX_AGE_MIN)
    if latest is None or too_old:
        refresh_service_metrics()


# ------------------------------------------------------------------ analytics
def overview():
    ensure_metrics_fresh()
    # $facet: several independent aggregations in ONE query
    facets = list(db.queue_events.aggregate([
        {"$facet": {
            "totals": [
                {"$group": {
                    "_id": None,
                    "events": {"$sum": 1},
                    "served": {"$sum": {"$cond": [
                        {"$eq": ["$event_type", "service_completed"]}, 1, 0]}},
                    "first": {"$min": "$timestamp"},
                    "last": {"$max": "$timestamp"},
                }},
            ],
            "served_by_weekday": [
                {"$match": {"event_type": "service_completed"}},
                # stage 1: students served on each calendar date
                {"$group": {
                    "_id": {
                        "dow": {"$dayOfWeek": _ist("$timestamp")},
                        "date": {"$dateToString": {"format": "%Y-%m-%d",
                                                   "date": "$timestamp", "timezone": TZ}},
                    },
                    "served": {"$sum": 1},
                }},
                # stage 2: average of those daily totals per weekday
                {"$group": {"_id": "$_id.dow", "avg_served": {"$avg": "$served"}}},
                {"$sort": {"_id": 1}},
            ],
        }},
    ]))[0]

    totals = facets["totals"][0] if facets["totals"] else None
    wait = list(db.wait_observations.aggregate([
        {"$group": {"_id": None, "avg": {"$avg": "$actual_wait_min"}}},
    ]))
    busiest = list(db.service_metrics.aggregate([
        {"$sort": {"avg_waiting": -1}},
        {"$limit": 5},
        *_with_location_name(),
        {"$project": {"_id": 0, "computed_at": 0}},
    ]))
    latest = db.service_metrics.find_one({}, sort=[("computed_at", -1)])

    return {
        "events": totals["events"] if totals else 0,
        "served": totals["served"] if totals else 0,
        "days_of_history": (totals["last"] - totals["first"]).days + 1 if totals else 0,
        "avg_actual_wait_min": round(wait[0]["avg"], 1) if wait else None,
        "served_by_weekday": [
            {"day": DAY_NAMES[d["_id"]], "avg_served": round(d["avg_served"])}
            for d in facets["served_by_weekday"]
        ],
        "busiest_slots": [{**s, "day": DAY_NAMES[s["day_of_week"]]} for s in busiest],
        "metrics": {
            "documents": db.service_metrics.count_documents({}),
            "computed_at": latest["computed_at"].isoformat() if latest else None,
        },
    }


def hourly_peaks():
    """Average queue length per location per hour, computed from raw events."""
    docs = db.queue_events.aggregate([
        {"$match": {"event_type": "queue_update"}},
        # stage 1: one group per (location, hour)
        {"$group": {
            "_id": {"location_id": "$location_id", "hour": {"$hour": _ist("$timestamp")}},
            "avg": {"$avg": "$waiting_count"},
            "max": {"$max": "$waiting_count"},
        }},
        {"$sort": {"_id.hour": 1}},
        # stage 2: collect the hours of each location into one array
        {"$group": {
            "_id": "$_id.location_id",
            "hours": {"$push": {"hour": "$_id.hour",
                                "avg": {"$round": ["$avg", 1]}, "max": "$max"}},
        }},
        {"$set": {"location_id": "$_id"}},
        *_with_location_name(),
        {"$project": {"_id": 0}},
        {"$sort": {"location_id": 1}},
    ])
    result = []
    for d in docs:
        peak = max(d["hours"], key=lambda h: h["avg"])
        d["peak_hour"], d["peak_avg"] = peak["hour"], peak["avg"]
        result.append(d)
    return result


def service_speed():
    return list(db.queue_events.aggregate([
        {"$match": {"event_type": "service_completed",
                    "service_duration_seconds": {"$exists": True}}},
        {"$group": {
            "_id": "$location_id",
            "avg": {"$avg": "$service_duration_seconds"},
            "min": {"$min": "$service_duration_seconds"},
            "max": {"$max": "$service_duration_seconds"},
            "std": {"$stdDevPop": "$service_duration_seconds"},
            "served": {"$sum": 1},
        }},
        {"$set": {"location_id": "$_id"}},
        *_with_location_name(),
        {"$project": {
            "_id": 0, "location_id": 1, "name": 1, "served": 1,
            "avg": {"$round": ["$avg", 1]}, "min": {"$round": ["$min", 1]},
            "max": {"$round": ["$max", 1]}, "std": {"$round": ["$std", 1]},
        }},
        {"$sort": {"avg": -1}},
    ]))


def heatmap(location_id):
    """Reads precomputed metrics - fast, uses the (location, day, hour) index."""
    ensure_metrics_fresh()
    cells = list(db.service_metrics.find(
        {"location_id": location_id},
        {"_id": 0, "day_of_week": 1, "hour": 1, "avg_waiting": 1, "max_waiting": 1},
    ).sort([("day_of_week", 1), ("hour", 1)]))
    for c in cells:
        c["day"] = DAY_NAMES[c["day_of_week"]]
    return cells


def forecast(location_id):
    """Expected wait for each hour today, based on the same weekday in the past."""
    ensure_metrics_fresh()
    loc = db.locations.find_one({"location_id": location_id}, {"_id": 0})
    if loc is None:
        return None
    live = db.queue_status.find_one({"location_id": location_id}, {"_id": 0})

    now = now_ist()
    dow = now.isoweekday() % 7 + 1          # Python Mon=1..Sun=7 -> MongoDB Sun=1..Sat=7
    counters = loc["default_counters"]
    oh, om = map(int, loc["opening_hours"]["open"].split(":"))
    ch, cm = map(int, loc["opening_hours"]["close"].split(":"))
    open_min, close_min = oh * 60 + om, ch * 60 + cm
    closed_today = now.strftime("%A") in loc.get("closed_on", [])

    slots = []
    if not closed_today:
        for m in db.service_metrics.find({"location_id": location_id,
                                          "day_of_week": dow}).sort("hour", 1):
            hour = m["hour"]
            if not (open_min < (hour + 1) * 60 and hour * 60 < close_min):
                continue
            svc = m.get("avg_service_seconds", live["avg_service_seconds"])
            slots.append({
                "hour": hour,
                "avg_waiting": round(m["avg_waiting"], 1),
                "expected_wait_min": estimate_wait_minutes(m["avg_waiting"], svc, counters),
                "is_past": hour < now.hour,
            })

    upcoming = [s for s in slots if not s["is_past"]]
    best = min(upcoming, key=lambda s: s["expected_wait_min"]) if upcoming else None
    return {
        "location_id": location_id,
        "name": loc["name"],
        "day": DAY_NAMES[dow],
        "current_hour": now.hour,
        "closed_today": closed_today,
        "slots": slots,
        "best_hour": best["hour"] if best else None,
        "best_wait_min": best["expected_wait_min"] if best else None,
    }