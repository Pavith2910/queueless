"""
add_walk_times.py - Adds walking times between nearby locations
(schema evolution: a new embedded field on existing documents)
and creates a multikey index on available_services.

Run from project root:  python -m scripts.add_walk_times
(Re-run this after setup_db if you ever reset the database.)
"""
from pymongo import UpdateOne

from db import db

# Walking minutes between locations (same in both directions)
WALK = {
    ("CANTEEN_A", "CANTEEN_B"): 4,
    ("CANTEEN_A", "SNACK_KIOSK"): 3,
    ("CANTEEN_B", "SNACK_KIOSK"): 5,
    ("OFFICE_A", "OFFICE_B"): 2,
}


def main():
    walk = {}
    for (a, b), minutes in WALK.items():
        walk.setdefault(a, {})[b] = minutes
        walk.setdefault(b, {})[a] = minutes

    # bulk_write: several updates sent to MongoDB in ONE round trip
    ops = [UpdateOne({"location_id": loc}, {"$set": {"walk_minutes": w}})
           for loc, w in walk.items()]
    result = db.locations.bulk_write(ops)
    print(f"Updated {result.modified_count} locations with walk_minutes")

    # Index on an ARRAY field = multikey index (one entry per array element)
    db.locations.create_index("available_services", name="by_service")
    print("Created multikey index 'by_service' on available_services")

    for doc in db.locations.find({}, {"_id": 0, "location_id": 1, "walk_minutes": 1}):
        print("  ", doc)


if __name__ == "__main__":
    main()