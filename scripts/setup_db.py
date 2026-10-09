"""
setup_db.py - Creates QueueLess collections with validation rules,
creates indexes, and seeds the starting locations.

WARNING: Running this RESETS the database (drops the 4 collections).

Run from the project root folder:
    python -m scripts.setup_db
"""
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import WriteError

from db import db

COLLECTIONS = ["locations", "queue_status", "queue_events", "service_metrics"]

# ---------------------------------------------------------------------------
# 1. VALIDATION RULES ($jsonSchema)
#    "required" fields must exist; extra fields are still allowed,
#    so the schema stays flexible.
# ---------------------------------------------------------------------------
TIME_PATTERN = "^([01][0-9]|2[0-3]):[0-5][0-9]$"   # "HH:MM"

VALIDATORS = {
    "locations": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["location_id", "name", "category", "group",
                         "opening_hours", "available_services"],
            "properties": {
                "location_id": {"bsonType": "string", "pattern": "^[A-Z0-9_]+$"},
                "name": {"bsonType": "string", "minLength": 2},
                "category": {"enum": ["canteen", "office", "library", "clinic"]},
                "group": {"bsonType": "string",
                          "description": "Locations in the same group can replace each other"},
                "opening_hours": {
                    "bsonType": "object",
                    "required": ["open", "close"],
                    "properties": {
                        "open": {"bsonType": "string", "pattern": TIME_PATTERN},
                        "close": {"bsonType": "string", "pattern": TIME_PATTERN},
                    },
                },
                "available_services": {"bsonType": "array",
                                       "items": {"bsonType": "string"}},
            },
        }
    },
    "queue_status": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["location_id", "current_waiting", "active_counters",
                         "avg_service_seconds", "status", "updated_at"],
            "properties": {
                "location_id": {"bsonType": "string"},
                "current_waiting": {"bsonType": "number", "minimum": 0},
                "active_counters": {"bsonType": "number", "minimum": 0},
                "avg_service_seconds": {"bsonType": "number", "minimum": 1},
                "status": {"enum": ["low", "moderate", "busy", "closed"]},
                "updated_at": {"bsonType": "date"},
            },
        }
    },
    "queue_events": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["location_id", "event_type", "waiting_count", "timestamp"],
            "properties": {
                "location_id": {"bsonType": "string"},
                "event_type": {"enum": ["queue_update", "service_completed",
                                        "counter_change"]},
                "waiting_count": {"bsonType": "number", "minimum": 0},
                "served_count": {"bsonType": "number", "minimum": 0},
                "active_counters": {"bsonType": "number", "minimum": 0},
                "service_duration_seconds": {"bsonType": "number", "minimum": 1},
                "timestamp": {"bsonType": "date"},
            },
        }
    },
    "service_metrics": {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["location_id", "day_of_week", "hour",
                         "avg_waiting", "sample_count", "computed_at"],
            "properties": {
                "location_id": {"bsonType": "string"},
                "day_of_week": {"bsonType": "number", "minimum": 1, "maximum": 7},
                "hour": {"bsonType": "number", "minimum": 0, "maximum": 23},
                "avg_waiting": {"bsonType": "number", "minimum": 0},
                "avg_service_seconds": {"bsonType": "number", "minimum": 0},
                "sample_count": {"bsonType": "number", "minimum": 0},
                "computed_at": {"bsonType": "date"},
            },
        }
    },
}

# ---------------------------------------------------------------------------
# 2. SEED DATA - notice each category has its OWN extra fields
#    (flexible schema demonstration)
# ---------------------------------------------------------------------------
LOCATIONS = [
    {
        "location_id": "CANTEEN_A", "name": "Main Canteen",
        "category": "canteen", "group": "food",
        "opening_hours": {"open": "08:00", "close": "20:00"},
        "available_services": ["meals", "snacks", "beverages"],
        "default_counters": 2, "default_service_seconds": 50,
        "menu_tags": ["south_indian", "north_indian", "chinese"],
        "veg_only": False,
    },
    {
        "location_id": "CANTEEN_B", "name": "Food Court",
        "category": "canteen", "group": "food",
        "opening_hours": {"open": "09:00", "close": "19:00"},
        "available_services": ["meals", "snacks", "beverages"],
        "default_counters": 2, "default_service_seconds": 45,
        "menu_tags": ["south_indian", "chaat", "juices"],
        "veg_only": True,
    },
    {
        "location_id": "SNACK_KIOSK", "name": "Snack Kiosk",
        "category": "canteen", "group": "food",
        "opening_hours": {"open": "07:30", "close": "21:00"},
        "available_services": ["snacks", "beverages"],
        "default_counters": 1, "default_service_seconds": 30,
        "menu_tags": ["tea", "coffee", "puffs"],
        "veg_only": False,
    },
    {
        "location_id": "OFFICE_A", "name": "Student Office",
        "category": "office", "group": "admin",
        "opening_hours": {"open": "09:30", "close": "16:30"},
        "available_services": ["bonafide_certificate", "transcript", "id_card"],
        "default_counters": 1, "default_service_seconds": 120,
        "documents_required": ["college_id"],
        "closed_on": ["Sunday"],
    },
    {
        "location_id": "OFFICE_B", "name": "Accounts Section",
        "category": "office", "group": "admin",
        "opening_hours": {"open": "10:00", "close": "16:00"},
        "available_services": ["fee_payment", "fee_receipt", "transcript"],
        "default_counters": 2, "default_service_seconds": 150,
        "documents_required": ["college_id", "fee_challan"],
        "closed_on": ["Sunday"],
    },
    {
        "location_id": "LIBRARY", "name": "Central Library Desk",
        "category": "library", "group": "library",
        "opening_hours": {"open": "08:00", "close": "21:00"},
        "available_services": ["book_issue", "book_return"],
        "default_counters": 2, "default_service_seconds": 40,
        "total_seats": 250, "floor": "Ground",
    },
]


# ---------------------------------------------------------------------------
# 3. FUNCTIONS
# ---------------------------------------------------------------------------
def reset_collections():
    print("\n[1] Creating collections with validation rules...")
    for name in COLLECTIONS:
        db.drop_collection(name)
        db.create_collection(
            name,
            validator=VALIDATORS[name],
            validationLevel="strict",   # check every insert and update
            validationAction="error",   # reject invalid documents
        )
        print(f"    created: {name}")


def create_indexes():
    print("\n[2] Creating indexes...")
    db.locations.create_index("location_id", unique=True, name="uniq_location_id")
    db.locations.create_index("group", name="by_group")

    db.queue_status.create_index("location_id", unique=True, name="uniq_status_location")
    db.queue_status.create_index("status", name="by_status")

    db.queue_events.create_index(
        [("location_id", ASCENDING), ("timestamp", DESCENDING)],
        name="loc_time",
    )

    db.service_metrics.create_index(
        [("location_id", ASCENDING), ("day_of_week", ASCENDING), ("hour", ASCENDING)],
        unique=True, name="uniq_loc_day_hour",
    )
    for name in COLLECTIONS:
        names = [ix["name"] for ix in db[name].list_indexes()]
        print(f"    {name}: {names}")


def seed_data():
    print("\n[3] Seeding locations and initial queue status...")
    now = datetime.now(timezone.utc)
    db.locations.insert_many([dict(loc) for loc in LOCATIONS])

    status_docs = [
        {
            "location_id": loc["location_id"],
            "current_waiting": 0,
            "active_counters": loc["default_counters"],
            "avg_service_seconds": loc["default_service_seconds"],
            "status": "low",
            "updated_at": now,
        }
        for loc in LOCATIONS
    ]
    db.queue_status.insert_many(status_docs)
    print(f"    locations: {db.locations.count_documents({})}")
    print(f"    queue_status: {db.queue_status.count_documents({})}")


def test_validation():
    print("\n[4] Testing validation (these SHOULD be rejected)...")
    bad_docs = [
        ("negative queue length", "queue_status", {
            "location_id": "CANTEEN_A", "current_waiting": -5,
            "active_counters": 1, "avg_service_seconds": 30,
            "status": "low", "updated_at": datetime.now(timezone.utc)}),
        ("invalid status value", "queue_status", {
            "location_id": "CANTEEN_A", "current_waiting": 3,
            "active_counters": 1, "avg_service_seconds": 30,
            "status": "super_busy", "updated_at": datetime.now(timezone.utc)}),
        ("missing timestamp", "queue_events", {
            "location_id": "CANTEEN_A", "event_type": "queue_update",
            "waiting_count": 4}),
    ]
    for label, coll, doc in bad_docs:
        try:
            db[coll].insert_one(doc)
            print(f"    [FAIL] accepted bad document: {label}")
        except WriteError:
            print(f"    [OK]   rejected: {label}")


if __name__ == "__main__":
    print(f"Setting up database '{db.name}' (this resets it)...")
    reset_collections()
    create_indexes()
    seed_data()
    test_validation()
    print("\nDone. Database is ready.")