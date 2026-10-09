"""
generate_data.py - Simulates realistic queue activity for the last 14 days
plus today (up to the current time) and stores it in MongoDB.

Each simulated student: arrives -> waits in a FIFO queue -> is served by
the first free counter. From this we record:
  * queue_events      : snapshots every 5 min + every service completion
  * wait_observations : formula estimate vs ACTUAL wait for every student
                        (ground truth for accuracy testing in Step 10)
  * queue_status      : the live state of each queue right now

Re-running replaces old simulated data (locations are not touched).
Run from the project root:
    python -m scripts.generate_data
"""
import bisect
import math
import random
from datetime import datetime, timedelta, timezone

from pymongo import ASCENDING

from db import db
from services.wait_time import estimate_wait_minutes, crowd_status

IST = timezone(timedelta(hours=5, minutes=30))   # India has no daylight saving
UTC = timezone.utc
DAYS_BACK = 14
SNAPSHOT_EVERY_MIN = 5
EXAM_DAYS = 4          # library is busier in the last 4 days (exam week)
random.seed(42)        # same "random" numbers each run -> reproducible

# Average number of students ARRIVING PER MINUTE, by hour of day (IST).
# Hours not listed use 0.2. Compare with capacity = counters x 60 / service_sec
# e.g. Main Canteen: 2 x 60 / 50 = 2.4 per minute. At 13:00 arrivals (2.8)
# exceed capacity, so the queue builds up - that is our lunch rush.
HOURLY_RATES = {
    "CANTEEN_A":   {8: 0.6, 9: 0.8, 10: 1.2, 11: 0.9, 12: 2.2, 13: 2.8,
                    14: 1.0, 15: 1.3, 16: 1.6, 17: 0.8, 18: 0.6, 19: 0.4},
    "CANTEEN_B":   {9: 0.5, 10: 0.9, 11: 0.7, 12: 1.5, 13: 1.9, 14: 0.8,
                    15: 1.0, 16: 1.2, 17: 0.6, 18: 0.4},
    "SNACK_KIOSK": {7: 0.6, 8: 1.2, 9: 0.8, 10: 1.5, 11: 0.9, 12: 1.0,
                    13: 1.1, 14: 0.8, 15: 1.4, 16: 1.8, 17: 1.2, 18: 0.8,
                    19: 0.6, 20: 0.4},
    "OFFICE_A":    {9: 0.3, 10: 0.45, 11: 0.5, 12: 0.4, 13: 0.2, 14: 0.35,
                    15: 0.3, 16: 0.2},
    "OFFICE_B":    {10: 0.7, 11: 0.9, 12: 0.7, 13: 0.3, 14: 0.6, 15: 0.5},
    "LIBRARY":     {8: 0.5, 9: 0.8, 10: 1.0, 11: 1.1, 12: 1.3, 13: 1.6,
                    14: 1.0, 15: 1.2, 16: 1.5, 17: 1.4, 18: 0.9, 19: 0.6,
                    20: 0.4},
}


def poisson(lam):
    """Random number of arrivals in one minute (Poisson distribution)."""
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= random.random()
        if p <= limit:
            return k
        k += 1


def at(day, hhmm):
    """Combine a date and 'HH:MM' into an IST datetime."""
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=IST)


def day_factor(loc, day, today):
    """How busy this day is compared with a normal weekday."""
    cat, weekday = loc["category"], day.weekday()   # Monday=0 ... Sunday=6
    if weekday == 6:                                 # Sunday
        if cat == "office":
            return 0.0                               # offices closed
        factor = 0.4 if cat == "canteen" else 0.5
    elif weekday == 5:                               # Saturday
        factor = 0.5 if cat == "office" else 0.6
    else:
        factor = 1.0
    if cat == "library" and (today - day).days < EXAM_DAYS:
        factor *= 1.6                                # exam week rush
    return factor * random.uniform(0.85, 1.15)       # day-to-day variation


def simulate_day(loc, day, today, now):
    """Simulates one location for one day. Returns (events, observations, live_state)."""
    loc_id = loc["location_id"]
    counters = loc["default_counters"]
    mean_service = loc["default_service_seconds"]
    open_t = at(day, loc["opening_hours"]["open"])
    close_t = at(day, loc["opening_hours"]["close"])
    factor = day_factor(loc, day, today)
    arrival_end = min(close_t, now)

    if factor == 0 or arrival_end <= open_t:
        return [], [], None                          # closed or not opened yet

    # 1) Generate arrival times
    arrivals = []
    t = open_t
    while t < arrival_end:
        lam = HOURLY_RATES[loc_id].get(t.hour, 0.2) * factor
        for _ in range(poisson(lam)):
            a = t + timedelta(seconds=random.uniform(0, 60))
            if a < arrival_end:
                arrivals.append(a)
        t += timedelta(minutes=1)
    arrivals.sort()

    # 2) Serve them first-come-first-served at the earliest free counter
    free_at = [open_t] * counters
    starts, ends, durations = [], [], []
    for a in arrivals:
        i = min(range(counters), key=lambda k: free_at[k])
        start = max(a, free_at[i])
        duration = max(5.0, random.gammavariate(4, mean_service / 4))  # varies around the mean
        free_at[i] = start + timedelta(seconds=duration)
        starts.append(start)
        ends.append(free_at[i])
        durations.append(duration)

    def waiting_at(moment):
        """People who have arrived but not yet started service."""
        return bisect.bisect_right(arrivals, moment) - bisect.bisect_right(starts, moment)

    events, observations = [], []

    # 3a) Snapshot every 5 minutes (like a staff member updating the count)
    t = open_t
    while t <= min(close_t, now):
        events.append({
            "location_id": loc_id,
            "event_type": "queue_update",
            "waiting_count": waiting_at(t),
            "active_counters": counters,
            "timestamp": t.astimezone(UTC),
        })
        t += timedelta(minutes=SNAPSHOT_EVERY_MIN)

    # 3b) One event per completed service
    order = sorted(range(len(arrivals)), key=lambda k: ends[k])
    served = 0
    for k in order:
        if ends[k] > now:
            break
        served += 1
        events.append({
            "location_id": loc_id,
            "event_type": "service_completed",
            "waiting_count": waiting_at(ends[k]),
            "served_count": served,                  # served so far today
            "active_counters": counters,
            "service_duration_seconds": round(durations[k], 1),
            "timestamp": ends[k].astimezone(UTC),
        })

    # 3c) Estimated vs actual wait for every student who got served
    for k, a in enumerate(arrivals):
        if starts[k] > now:
            continue
        ahead = k - bisect.bisect_right(starts, a, 0, k)
        observations.append({
            "location_id": loc_id,
            "joined_at": a.astimezone(UTC),
            "people_ahead": ahead,
            "active_counters": counters,
            "estimated_wait_min": estimate_wait_minutes(ahead, mean_service, counters),
            "actual_wait_min": round((starts[k] - a).total_seconds() / 60, 2),
        })

    # 4) The live state right now (only for today)
    state = None
    if day == today:
        recent = [durations[k] for k in order if ends[k] <= now][-30:]
        state = {
            "is_open": open_t <= now < close_t,
            "waiting": waiting_at(now),
            "avg_service": round(sum(recent) / len(recent)) if recent else mean_service,
        }
    return events, observations, state


def update_live_status(loc, state, now):
    """Writes the current queue condition into queue_status (overwrite, not insert)."""
    if state is None or not state["is_open"]:
        fields = {
            "current_waiting": 0,
            "active_counters": 0,
            "avg_service_seconds": loc["default_service_seconds"],
            "status": "closed",
        }
    else:
        counters = loc["default_counters"]
        est = estimate_wait_minutes(state["waiting"], state["avg_service"], counters)
        fields = {
            "current_waiting": state["waiting"],
            "active_counters": counters,
            "avg_service_seconds": state["avg_service"],
            "status": crowd_status(est),
        }
    fields["updated_at"] = now.astimezone(UTC)
    db.queue_status.update_one({"location_id": loc["location_id"]}, {"$set": fields})
    return fields


def main():
    locations = list(db.locations.find({}, {"_id": 0}))
    if not locations:
        print("No locations found. Run  python -m scripts.setup_db  first.")
        return

    now = datetime.now(IST)
    today = now.date()
    print(f"Simulating {DAYS_BACK} days + today (up to {now:%H:%M} IST)...\n")

    # Clear previous simulated data
    db.queue_events.delete_many({})
    db.service_metrics.delete_many({})
    db.drop_collection("wait_observations")
    db.wait_observations.create_index(
        [("location_id", ASCENDING), ("joined_at", ASCENDING)], name="loc_joined"
    )

    print(f"{'Location':<14}{'Students':>9}{'Events':>9}{'Avg wait':>10}{'Max wait':>10}   Right now")
    for loc in locations:
        all_events, all_obs, today_state = [], [], None
        for back in range(DAYS_BACK, -1, -1):
            day = today - timedelta(days=back)
            events, obs, state = simulate_day(loc, day, today, now)
            all_events += events
            all_obs += obs
            if day == today:
                today_state = state

        if all_events:
            db.queue_events.insert_many(all_events, ordered=False)
        if all_obs:
            db.wait_observations.insert_many(all_obs, ordered=False)
        live = update_live_status(loc, today_state, now)

        waits = [o["actual_wait_min"] for o in all_obs]
        avg = sum(waits) / len(waits) if waits else 0
        worst = max(waits) if waits else 0
        print(f"{loc['location_id']:<14}{len(all_obs):>9}{len(all_events):>9}"
              f"{avg:>9.1f}m{worst:>9.1f}m   {live['status']} ({live['current_waiting']} waiting)")

    print(f"\nTotal queue_events:      {db.queue_events.count_documents({}):,}")
    print(f"Total wait_observations: {db.wait_observations.count_documents({}):,}")
    print("Done.")


if __name__ == "__main__":
    main()