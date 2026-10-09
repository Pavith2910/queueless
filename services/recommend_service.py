"""
recommend_service.py - Suggests a less-crowded alternative location.

Rules:
  * same group (food -> food) and offers the wanted service
  * open right now
  * total time = walking time + estimated wait
  * recommend switching only if it saves at least MIN_SAVING_MIN minutes
"""
from db import db
from services.queue_service import get_all_queues

MIN_SAVING_MIN = 2
DEFAULT_WALK_MIN = 5


class RecommendError(Exception):
    pass


def _summary(q):
    return {k: q[k] for k in ("location_id", "name", "is_open", "status",
                              "waiting", "est_wait_min", "trend_direction")}


def recommend(location_id, service=None):
    origin = db.locations.find_one({"location_id": location_id}, {"_id": 0})
    if origin is None:
        raise RecommendError(f"Unknown location '{location_id}'")
    if service and service not in origin["available_services"]:
        raise RecommendError(f"{origin['name']} does not offer '{service}'")

    wanted = [service] if service else origin["available_services"]

    # Query on an ARRAY field: a plain value means "array contains it",
    # $in means "array contains any of these". Uses the multikey index.
    candidates = list(db.locations.find(
        {
            "group": origin["group"],
            "location_id": {"$ne": location_id},
            "available_services": service if service else {"$in": wanted},
        },
        {"_id": 0, "location_id": 1, "available_services": 1},
    ))

    live = {q["location_id"]: q for q in get_all_queues()}
    here = live[location_id]
    walk_map = origin.get("walk_minutes", {})

    options = []
    for c in candidates:
        q = live.get(c["location_id"])
        if q is None or not q["is_open"]:
            continue
        walk = walk_map.get(c["location_id"], DEFAULT_WALK_MIN)
        covered = [s for s in wanted if s in c["available_services"]]
        options.append({
            **_summary(q),
            "walk_min": walk,
            "total_min": round(walk + q["est_wait_min"], 1),
            "services_covered": covered,
            "covers_all": len(covered) == len(wanted),
        })
    # places offering everything first, then the fastest
    options.sort(key=lambda o: (not o["covers_all"], o["total_min"]))
    best = options[0] if options else None

    verdict, saving = "stay", None
    if not here["is_open"]:
        if best:
            verdict = "switch"
            message = (f"{here['name']} is closed now. {best['name']} is open — "
                       f"about {best['total_min']} min including a {best['walk_min']}-min walk.")
        else:
            verdict = "none"
            message = f"{here['name']} is closed and no open alternative offers this service."
    elif best and here["est_wait_min"] - best["total_min"] >= MIN_SAVING_MIN:
        verdict = "switch"
        saving = round(here["est_wait_min"] - best["total_min"], 1)
        message = (f"Go to {best['name']} — about {saving} min faster, "
                   f"even with a {best['walk_min']}-min walk.")
    elif best:
        message = (f"Stay at {here['name']}. No nearby option saves at least "
                   f"{MIN_SAVING_MIN} minutes.")
    else:
        message = f"Stay at {here['name']}. No open alternative offers this service."

    if verdict == "switch" and best:
        if best["trend_direction"] == "rising":
            message += " Its queue is growing, so go soon."
        if not best["covers_all"]:
            message += f" Note: it only offers {', '.join(best['services_covered'])}."

    return {
        "origin": {**_summary(here), "services": origin["available_services"]},
        "service": service,
        "verdict": verdict,            # "switch", "stay" or "none"
        "saving_min": saving,
        "message": message,
        "recommended": best if verdict == "switch" else None,
        "options": options,
    }