from pymongo import MongoClient
from config import Config

# One client for the whole app. MongoClient manages a pool of connections
# internally, so we create it once and reuse it everywhere.
client = MongoClient(
    Config.MONGO_URI,
    serverSelectionTimeoutMS=3000,  # fail fast if MongoDB is not running
    tz_aware=True,                  # dates come back with timezone info
)

db = client[Config.DB_NAME]


def ping():
    """Raises an error if MongoDB is unreachable."""
    client.admin.command("ping")
    return True